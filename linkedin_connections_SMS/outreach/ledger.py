"""The ledger module: everything about Complete.md.

Deep module — all knowledge of the ledger format, dedup semantics, and daily
budget accounting sits behind these functions. Formats handled:

    - Name (YYYY-MM-DD HH:MM:SS) - SENT - https://profile/url/
    - Name (YYYY-MM-DD HH:MM:SS) - FAILED
    - Name (YYYY-MM-DD HH:MM:SS) - UNKNOWN
    - Name (YYYY-MM-DD HH:MM:SS) - SKIPPED   (live thread already had messages)
    - Name (YYYY-MM-DD HH:MM:SS)                  (legacy, counts as SENT)

The "done" statuses (SENT, UNKNOWN, SKIPPED) must never be messaged again.
Only SENT/UNKNOWN consume the daily budget — a SKIPPED contact was never sent
to in this run, so it costs no quota.
"""
import datetime
import os
import re

from outreach.config import LEDGER_FILE
from outreach.names import norm_name, profile_slug

#: Statuses that mean "never message this contact again". SKIPPED is included
#: because it is set only when the live LinkedIn thread already had messages.
DONE_STATUSES = ("SENT", "UNKNOWN", "SKIPPED")

LEDGER_RE = re.compile(
    r"^-\s+(.+?)\s+\((\d{4}-\d{2}-\d{2})[^)]*\)\s*(?:-\s*([A-Z]+)\b)?\s*(?:-\s*(https?://\S+))?\s*$"
)


def parse_ledger():
    """Parse Complete.md into entry dicts: name, norm, slug, date, status, url.
    Legacy lines without a status marker count as SENT."""
    entries = []
    if not os.path.exists(LEDGER_FILE):
        return entries
    with open(LEDGER_FILE, encoding="utf-8") as f:
        for line in f:
            m = LEDGER_RE.match(line.strip())
            if not m:
                continue
            entries.append({
                "name": m.group(1).strip(),
                "norm": norm_name(m.group(1)),
                "slug": profile_slug(m.group(4) or ""),
                "date": m.group(2),
                "status": m.group(3) or "SENT",
                "url": m.group(4) or "",
            })
    return entries


def sent_keys(entries):
    """(names, slugs) of entries that must never be messaged again:
    SENT (delivered), UNKNOWN (possibly delivered), and SKIPPED (the live
    thread already had messages). FAILED stays retryable."""
    names, slugs = set(), set()
    for e in entries:
        if e["status"] in DONE_STATUSES:
            names.add(e["norm"])
            if e["slug"]:
                slugs.add(e["slug"])
    return names, slugs


def is_messaged(contact, entries, sent_names, sent_slugs):
    """A contact is done if its profile slug was SENT/UNKNOWN, or its name was
    and cannot be distinguished from an earlier entry.

    Same name, different profile: if any done entry under that name carries a
    URL and none matches this contact's slug, it is a DIFFERENT person and
    must not be skipped. Legacy entries without URLs stay name-matched."""
    slug = profile_slug(contact.get("profile_url") or contact.get("compose_url") or "")
    if slug and slug in sent_slugs:
        return True
    n = norm_name(contact.get("name", ""))
    if not n or n not in sent_names:
        return False
    done_slugs_for_name = [e["slug"] for e in entries
                           if e["status"] in DONE_STATUSES and e["norm"] == n and e["slug"]]
    if done_slugs_for_name and slug and slug not in done_slugs_for_name:
        return False
    return True


def count_sent_today(entries, today=None):
    """SENT + UNKNOWN entries for today (UNKNOWN may have delivered, so it
    must consume daily budget — never overspend the cap)."""
    today = today or datetime.date.today().strftime("%Y-%m-%d")
    return len([e for e in entries
                if e["status"] in ("SENT", "UNKNOWN") and e["date"] == today])


def count_skipped(entries):
    """Contacts skipped because their live thread already had messages."""
    return len([e for e in entries if e["status"] == "SKIPPED"])


def append_ledger(name, status, url=""):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    url_part = f" - {url}" if url else ""
    with open(LEDGER_FILE, "a", encoding="utf-8") as f:
        f.write(f"- {name} ({ts}) - {status}{url_part}\n")
