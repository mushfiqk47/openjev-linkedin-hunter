import datetime
import os
import re

from outreach.config import LEDGER_FILE
from outreach.names import norm_name, profile_slug

DONE_STATUSES = ("SENT", "UNKNOWN", "SKIPPED")

LEDGER_RE = re.compile(
    r"^-\s+(.+?)\s+\((\d{4}-\d{2}-\d{2})[^)]*\)\s*(?:-\s*([A-Z]+)\b)?\s*(?:-\s*(https?://\S+))?\s*$"
)

def parse_ledger(ledger_file=None):

    target_file = ledger_file or LEDGER_FILE
    entries = []
    if not os.path.exists(target_file):
        return entries
    with open(target_file, encoding="utf-8") as f:
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

    names, slugs = set(), set()
    for e in entries:
        if e["status"] in DONE_STATUSES:
            names.add(e["norm"])
            if e["slug"]:
                slugs.add(e["slug"])
    return names, slugs

def is_messaged(contact, entries, sent_names, sent_slugs):

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

    today = today or datetime.date.today().strftime("%Y-%m-%d")
    return len([e for e in entries
                if e["status"] in ("SENT", "UNKNOWN") and e["date"] == today])

def count_skipped(entries):

    return len([e for e in entries if e["status"] == "SKIPPED"])

def append_ledger(name, status, url="", ledger_file=None):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    url_part = f" - {url}" if url else ""
    target_file = ledger_file or LEDGER_FILE
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(f"- {name} ({ts}) - {status}{url_part}\n")
