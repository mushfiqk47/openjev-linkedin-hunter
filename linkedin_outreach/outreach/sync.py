from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

from outreach.browser import run_bu_script
from outreach.config import DEFAULT_CONNECTIONS_URL, get_str
from outreach.harvest import CONNECTIONS_LINKS_JS, SEARCH_SWEEP_JS, search_page_url
from outreach.registry import ConnectionsRegistry, get_registry

def sync_network(
    registry: ConnectionsRegistry | None = None,
    target_new: int = 25,
    start_page: int = 1,
    max_search_pages: int = 20,
    search_only: bool = False,
    on_event: Callable[[str, str], None] | None = None,
) -> list[dict]:

    reg = registry or get_registry()
    log = on_event or (lambda msg, lvl="info": print(f"  [{lvl}] {msg}"))

    log(f"Synchronizing LinkedIn network state against registry ({reg.get_stats()['total_tracked']} tracked)...", "info")

    new_discovered: list[dict] = []
    connections_url = get_str("LINKEDIN_CONNECTIONS_URL", DEFAULT_CONNECTIONS_URL)

    if not search_only:
        log("Scanning recent connections page for newly added network members...", "info")
        script = CONNECTIONS_LINKS_JS.replace("__CONNECTIONS_URL__", connections_url)
        out, err = run_bu_script(script)
        for line in out.splitlines():
            if not line.startswith("LINKS:"):
                continue
            try:
                links = json.loads(line[len("LINKS:"):].strip())
            except Exception:
                links = []
            for link in links:
                label = link.get("label", "")
                raw_name = label[len("Send a message to "):].strip()
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://www.linkedin.com" + href

                if reg.is_done(href) or reg.is_done(raw_name):
                    continue

                rec, is_new = reg.sync_contact(raw_name, href, compose_url=href)
                if is_new:
                    new_discovered.append(rec)
                    log(f"New connection found: {rec['name']} ({rec['slug'] or 'no-slug'})", "match")

    unsent_pool = reg.get_unsent_pool()
    if len(unsent_pool) < target_new:
        log(f"Checking 1st-degree People Search for uncontacted connections (current unsent: {len(unsent_pool)})...", "info")
        empty_streak = 0
        for page in range(start_page, start_page + max_search_pages):
            if len(reg.get_unsent_pool()) >= target_new:
                break
            url = search_page_url(page)
            script = SEARCH_SWEEP_JS.replace("__SEARCH_URL__", url).replace("__MARKER__", "CARDS:")
            out, err = run_bu_script(script)
            items = []
            for line in out.splitlines():
                if line.startswith("CARDS:"):
                    try:
                        items = json.loads(line[len("CARDS:"):].strip())
                    except Exception:
                        items = []
                    break

            if not items:
                empty_streak += 1
                if empty_streak >= 3:
                    log(f"Search page {page} empty. Ending network sweep.", "info")
                    break
                continue

            empty_streak = 0
            page_new = 0
            for item in items:
                p_url = (item.get("profile_url") or "").split("?")[0]
                if p_url and not p_url.startswith("http"):
                    p_url = "https://www.linkedin.com" + p_url
                name = item.get("name", "")
                headline = item.get("headline", "")

                if reg.is_done(p_url) or reg.is_done(name):
                    continue

                rec, is_new = reg.sync_contact(name, p_url, headline=headline)
                if is_new:
                    page_new += 1
                    new_discovered.append(rec)

            log(f"Page {page}: scanned {len(items)} connections, found {page_new} unsent lead(s).", "info")

    reg.last_sync = datetime.now().isoformat()
    reg.save()

    active_unsent = reg.get_unsent_pool()
    log(f"Network sync complete. Total unsent candidates ready: {len(active_unsent)}", "success")
    return active_unsent
