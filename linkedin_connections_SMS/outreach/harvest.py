"""Contact harvesting: fill data/contacts.json with unsent 1st-degree connections.

Two strategies:
  A. Connections page (~9 cards) — quick top-up of recent connections.
  B. Paginated 1st-degree People Search (network=["F"]) — the bulk source.

Every contact is deduplicated against the ledger by name AND profile URL,
and within the file itself. Existing unsent contacts are preserved.
The harvester also captures each contact's headline for {headline} in the
message template.
"""
import json
import os
from pathlib import Path

from outreach.browser import run_bu_script
from outreach.config import (CONTACTS_FILE, DEFAULT_CONNECTIONS_URL, get_int, get_str)
from outreach.evaluator import evaluate_contact
from outreach.ledger import is_messaged, parse_ledger, sent_keys
from outreach.names import clean_display_name, norm_name

# Connections page: collect the "Send a message to X" compose links.
# Same navigation style as the other templates: js location.href + poll.
CONNECTIONS_LINKS_JS = """
import json, time

js(\"window.location.href = '__CONNECTIONS_URL__'\")
time.sleep(3)

# Poll until the connection cards render (max ~8s)
for i in range(8):
    ready = js('''(() => {
        return document.querySelectorAll('a[aria-label^=\"Send a message\"]').length > 0;
    })()''')
    if ready:
        break
    time.sleep(1)

# See-all: the connections page lazy-renders, so nudge it to load more cards
# before scraping (the People Search fallback still covers whatever stays hidden).
for i in range(4):
    js('''(() => {
        const main = document.querySelector('main') || document.body;
        if (main) main.scrollTop = main.scrollHeight;
        window.scrollTo(0, document.body.scrollHeight);
        return true;
    })()''')
    time.sleep(1)

links = js('''(() => {
    const out = [];
    document.querySelectorAll('a').forEach(a => {
        const label = a.getAttribute('aria-label') || '';
        if (label.startsWith('Send a message')) {
            out.push({ label: label, href: a.getAttribute('href') });
        }
    });
    return out;
})()''')
print(\"LINKS:\" + json.dumps(links))
"""

# One 1st-degree search page: wait for results, then scrape
# {name, headline, profile_url} from every /in/ card.
# Outer quotes are triple-DOUBLE; the inner js(...) calls use triple-single.
SEARCH_SWEEP_JS = """
import json, time

js(\"window.location.href = '__SEARCH_URL__'\")
time.sleep(3)

# Poll for search results to render instead of relying on a fixed sleep
for i in range(8):
    ready = js('''(() => {
        const main = document.querySelector('main');
        return !!(main && (main.querySelector('a[href*="/in/"]') || main.innerText.indexOf('No results') !== -1));
    })()''')
    if ready:
        break
    time.sleep(1)

# Force lazy-render of the full list
js('''(() => { window.scrollTo(0, document.body.scrollHeight / 2); return true; })()''')
time.sleep(1)
js('''(() => { window.scrollTo(0, document.body.scrollHeight); return true; })()''')
time.sleep(1)

cards = js('''(() => {
    const main = document.querySelector('main') || document.body;
    const anchors = Array.from(main.querySelectorAll('a[href*="/in/"]'));
    const results = [];
    const seenHrefs = new Set();
    const nl = String.fromCharCode(10);

    anchors.forEach(a => {
        let href = (a.getAttribute('href') || '').split('?')[0];
        let rawText = (a.innerText || '').trim();
        if (href.includes('/in/') && !href.endsWith('/in/') && !href.endsWith('/in/me/')) {
            if (!seenHrefs.has(href)) {
                seenHrefs.add(href);
                let lines = rawText.split(nl).map(s => s.trim()).filter(Boolean);
                let name = '';
                let nameIdx = -1;
                for (let li = 0; li < lines.length; li++) {
                    let clean = lines[li].replace('• 1st', '').replace('• 2nd', '').replace('• 3rd+', '').trim();
                    if (clean && !clean.toLowerCase().includes('mutual connection') && !clean.toLowerCase().includes('student') && !clean.toLowerCase().includes('designer') && !clean.toLowerCase().includes('developer')) {
                        name = clean;
                        nameIdx = li;
                        break;
                    }
                }
                if (!name && lines.length > 0) {
                    name = lines[0].replace('• 1st', '').trim();
                    nameIdx = 0;
                }
                let headline = '';
                if (nameIdx !== -1) {
                    for (let lj = nameIdx + 1; lj < lines.length && !headline; lj++) {
                        let l = lines[lj];
                        if (l.startsWith('•') || l === name) continue;
                        if (l.toLowerCase().includes('mutual connection') || l.toLowerCase().includes('follower')) continue;
                        headline = l;
                    }
                }
                if (name) {
                    results.push({ name: name, headline: headline, profile_url: href });
                }
            }
        }
    });
    return results;
})()''')

print(\"__MARKER__\" + json.dumps(cards))
"""


def run_search_sweep(search_url, marker="CARDS:"):
    """Run one search-page sweep; returns (items, raw_stdout, stderr)."""
    script = SEARCH_SWEEP_JS.replace("__SEARCH_URL__", search_url).replace("__MARKER__", marker)
    out, err = run_bu_script(script)
    items = []
    for line in out.splitlines():
        if line.startswith(marker):
            try:
                items = json.loads(line[len(marker):].strip())
            except Exception:
                items = []
            break
    return items, out, err


def search_page_url(page):
    return f"https://www.linkedin.com/search/results/people/?network=%5B%22F%22%5D&page={page}"


def load_existing_unsent(entries, sent_names, sent_slugs):
    """Existing unsent contacts from contacts.json, re-cleaned, keyed by name."""
    existing_map = {}
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, encoding="utf-8") as f:
                existing_contacts = json.load(f)
        except Exception:
            existing_contacts = []
        for c in existing_contacts:
            if "name" not in c or is_messaged(c, entries, sent_names, sent_slugs):
                continue
            c["name"] = clean_display_name(c["name"])
            existing_map[norm_name(c["name"])] = c
    return existing_map


def try_add(existing_map, entries, sent_names, sent_slugs, raw_name, profile_url, headline=""):
    """Add a contact if new (by name AND URL) and not already SENT. Returns True if added."""
    display_name = clean_display_name(raw_name)
    n_name = norm_name(raw_name)
    if not n_name or n_name in existing_map:
        return False
    candidate = {"name": display_name, "profile_url": profile_url}
    if is_messaged(candidate, entries, sent_names, sent_slugs):
        return False
    entry = {
        "name": display_name,
        "compose_url": profile_url,
        "profile_url": profile_url,
        "headline": clean_display_name(headline or ""),
    }
    # SemIf contact evaluation (archetype & relevance scoring)
    eval_res = evaluate_contact({"name": display_name, "headline": headline})
    entry["archetype"] = eval_res.get("archetype", "general")
    entry["relevance"] = eval_res.get("relevance", 60)
    existing_map[n_name] = entry
    return True


def harvest_connections_page(existing_map, entries, sent_names, sent_slugs, connections_url, target):
    """Strategy A: 'Send a message' links on the connections page."""
    script = CONNECTIONS_LINKS_JS.replace("__CONNECTIONS_URL__", connections_url)
    out, err = run_bu_script(script)
    added = 0
    for line in out.splitlines():
        if not line.startswith("LINKS:"):
            continue
        try:
            links = json.loads(line[len("LINKS:"):].strip())
        except Exception:
            links = []
        for link in links:
            if len(existing_map) >= target:
                break
            label = link.get("label", "")
            raw_name = label[len("Send a message to "):].strip()
            href = link.get("href", "")
            if not href.startswith("http"):
                href = "https://www.linkedin.com" + href
            if try_add(existing_map, entries, sent_names, sent_slugs, raw_name, href):
                added += 1
    if err and err.strip():
        print(f"[WARN] connections page sweep stderr: {err.strip()[:150]}")
    return added


def harvest_search_pages(existing_map, entries, sent_names, sent_slugs, target, start_page, max_pages):
    """Strategy B: paginated 1st-degree People Search sweep."""
    empty_streak = 0
    for page in range(start_page, start_page + max_pages):
        if len(existing_map) >= target:
            break
        items, _, err = run_search_sweep(search_page_url(page))
        if err and err.strip():
            print(f"[WARN] page {page} stderr: {err.strip()[:150]}")
        if not items:
            empty_streak += 1
            print(f"  page {page}: no cards found{'' if empty_streak < 3 else ' (stopping sweep)'}")
            if empty_streak >= 3:
                break
            continue
        empty_streak = 0
        added = 0
        for c in items:
            if len(existing_map) >= target:
                break
            profile_url = (c.get("profile_url") or "").split("?")[0]
            if not profile_url.startswith("http"):
                profile_url = "https://www.linkedin.com" + profile_url
            if try_add(existing_map, entries, sent_names, sent_slugs, c.get("name", ""),
                       profile_url, c.get("headline", "")):
                added += 1
        print(f"  page {page}: {len(items)} cards, {added} new")


def save_contacts(existing_map, target):
    contacts = list(existing_map.values())
    # Sort by relevance score descending so the most valuable connections are prioritized
    contacts.sort(key=lambda c: c.get("relevance", 60), reverse=True)
    contacts = contacts[:target]
    Path(CONTACTS_FILE).write_text(
        json.dumps(contacts, indent=2, ensure_ascii=False), encoding="utf-8")
    return contacts


def run(top=None, search_only=False, start_page=None, max_pages=None):
    """CLI: harvest unsent contacts into data/contacts.json."""
    target = top if top is not None else get_int("TOP_N", 25)
    connections_url = get_str("LINKEDIN_CONNECTIONS_URL", DEFAULT_CONNECTIONS_URL)
    start_page = start_page if start_page is not None else get_int("START_PAGE", 1)
    if search_only:
        max_pages = max_pages if max_pages is not None else get_int("MAX_PAGES", 10)
    else:
        max_pages = max_pages if max_pages is not None else get_int("SEARCH_MAX_PAGES", 50)

    entries = parse_ledger()
    sent_names, sent_slugs = sent_keys(entries)
    existing_map = load_existing_unsent(entries, sent_names, sent_slugs)

    print(f"Starting connection harvest (target: {target} unsent contacts, "
          f"already messaged: {len(sent_names)}, existing unsent: {len(existing_map)})...")

    if not search_only:
        added = harvest_connections_page(existing_map, entries, sent_names, sent_slugs,
                                         connections_url, target)
        print(f"Connections page: {added} new contacts (total {len(existing_map)}/{target})")

    if len(existing_map) < target:
        print("Paginating 1st-degree People Search for the rest...")
        harvest_search_pages(existing_map, entries, sent_names, sent_slugs, target, start_page, max_pages)

    contacts = save_contacts(existing_map, target)
    print(f"CONTACTS_SAVED ({len(contacts)} total pending):")
    for i, c in enumerate(contacts):
        print(f"  [{i + 1}] {c['name']} -> {c['compose_url']}")
    return contacts
