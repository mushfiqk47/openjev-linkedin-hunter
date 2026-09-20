"""Status reports and pre-flight diagnostics."""
import os
import subprocess
from datetime import date

from outreach.config import (DATA_DIR, DEFAULT_SEMIF_ENABLED, get_int)
from outreach.dispatch import load_pending
from outreach.evaluator import check_semif_connection
from outreach.ledger import count_sent_today, count_skipped, parse_ledger, sent_keys
from outreach.progress import refresh_progress

PREFLIGHT_FILES = [
    "Complete.md",
    "contacts.json",
    "message.py",
    ".env",
]


def run_stats():
    """CLI: print the quota + funnel report; refresh data/progress.txt."""
    today = date.today().strftime("%Y-%m-%d")
    daily_limit = get_int("DAILY_LIMIT", 15)

    entries = parse_ledger()
    sent_names, sent_slugs = sent_keys(entries)
    total_failed = len([e for e in entries if e["status"] == "FAILED"])
    total_unknown = len([e for e in entries if e["status"] == "UNKNOWN"])
    total_skipped = count_skipped(entries)
    sent_today = count_sent_today(entries)
    remaining_today = max(0, daily_limit - sent_today)
    pending = load_pending(entries, sent_names, sent_slugs)
    contacts_total = 0
    if pending is not None:
        contacts_file = os.path.join(DATA_DIR, "contacts.json")
        try:
            import json
            with open(contacts_file, encoding="utf-8") as f:
                contacts_total = len(json.load(f))
        except Exception:
            contacts_total = 0

    print("==================================================")
    print("       LINKEDIN OUTREACH AGENT - STATUS REPORT    ")
    print("==================================================")
    print(f"Date               : {today}")
    print(f"Total Logged       : {len(entries)} entries ({len(sent_names)} unique messaged)")
    print(f"Total Failed       : {total_failed} (retryable) | Unknown: {total_unknown} | Skipped: {total_skipped} (thread already had messages)")
    semif_enabled = get_int("SEMIF_ENABLED", DEFAULT_SEMIF_ENABLED) != 0
    semif_status = "active (LM Studio / qwen3.5-4b)" if semif_enabled else "disabled"
    print(f"Sent Today         : {sent_today} / {daily_limit} (Daily Limit)")
    print(f"Remaining Budget   : {remaining_today}")
    print(f"SemIf Engine       : {semif_status}")
    print("--------------------------------------------------")
    print(f"Contacts in File   : {contacts_total}")
    print(f"Pending Unsent     : {len(pending) if pending is not None else 0}")

    try:
        progress = refresh_progress()
        total_str = progress["total_connections"] if progress["total_connections"] is not None else "unknown (run `python agent.py progress`)"
        remaining_str = progress["remaining"] if progress["remaining"] is not None else "unknown"
        print("--------------------------------------------------")
        print(f"Total Connections  : {total_str}")
        print(f"Already Messaged   : {progress['messaged_unique']}")
        print(f"Remaining Network  : {remaining_str}")
        print(f"Saved to           : {os.path.join(DATA_DIR, 'progress.txt')}")
    except Exception as e:
        print(f"[WARN] could not refresh progress.txt: {e}")
    print("==================================================")


def _check_browser_use():
    try:
        p = subprocess.run(["browser-use", "--doctor"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=8)
        if "[ok  ] chrome running" in p.stdout and "[ok  ] daemon alive" in p.stdout:
            print("[PASS] Chrome CDP endpoint active & browser-use daemon connected")
            return True
        print("[FAIL] Chrome or browser-use daemon not ready")
        print(p.stdout)
        return False
    except FileNotFoundError:
        print("[FAIL] 'browser-use' CLI not found on PATH")
        return False
    except Exception as e:
        print(f"[FAIL] Error testing browser-use: {e}")
        return False


def run_preflight():
    """CLI: check browser/CDP, quota, SemIf backend, and required files before a session."""
    daily_limit = get_int("DAILY_LIMIT", 15)

    print("==================================================")
    print("     LINKEDIN OUTREACH AGENT - PREFLIGHT CHECK    ")
    print("==================================================")

    cdp_ok = _check_browser_use()

    semif_enabled = get_int("SEMIF_ENABLED", DEFAULT_SEMIF_ENABLED) != 0
    if semif_enabled:
        semif_ok, semif_msg = check_semif_connection()
        if semif_ok:
            print(f"[PASS] SemIf Decision Engine: {semif_msg}")
        else:
            print(f"[WARN] SemIf Decision Engine: {semif_msg} (will use heuristic fallback)")
    else:
        print("[INFO] SemIf Decision Engine: disabled (SEMIF_ENABLED=0)")

    sent_today = count_sent_today(parse_ledger())
    remaining = max(0, daily_limit - sent_today)
    print(f"[INFO] Daily usage: {sent_today} SENT today (budget: {remaining} remaining with DAILY_LIMIT={daily_limit})")

    for name in PREFLIGHT_FILES:
        full = os.path.join(DATA_DIR, name)
        if os.path.exists(full):
            print(f"[PASS] Found data/{name}")
        else:
            print(f"[WARN] Missing data/{name}")

    print("==================================================")
    if cdp_ok and remaining > 0:
        print(">>> PREFLIGHT STATUS: READY TO RUN OUTREACH <<<")
    elif cdp_ok and remaining == 0:
        print(">>> PREFLIGHT STATUS: CDP READY (DAILY QUOTA REACHED) <<<")
    else:
        print(">>> PREFLIGHT STATUS: ACTION REQUIRED BEFORE RUNNING <<<")
    print("==================================================")


def run_message_preview():
    """CLI: show the rendered message for all archetypes and where to edit it."""
    from outreach.messaging import build_message, get_template_for_archetype
    from outreach.evaluator import evaluate_contact

    archetypes = [
        ("Recruiter / Talent Partner", {"name": "Sarah Jenkins", "headline": "Senior Technical Recruiter at Acme"}),
        ("Founder / Executive", {"name": "Alex Rivera", "headline": "Founder & CEO at ScaleUI"}),
        ("Peer Designer", {"name": "David Chen", "headline": "Lead Product Designer at TechCorp"}),
        ("General / Default", {"name": "Sanzida Akter", "headline": "Frontend Developer"}),
    ]

    print("==================================================")
    print("        CURRENT OUTREACH MESSAGES (PREVIEW)       ")
    print("==================================================")
    print("Placeholders: {name} {portfolio} {headline} {archetype}\n")

    for title, sample in archetypes:
        eval_res = evaluate_contact(sample)
        sample["archetype"] = eval_res.get("archetype", "general")
        _, origin = get_template_for_archetype(sample["archetype"])
        print(f"--- Persona: {title} [{sample['archetype']}] ---")
        print(f"Template Source : {origin}")
        print("Message Preview :")
        print(build_message(sample["name"], sample))
        print("-" * 50)

    print("Edit the wording in data/message.py - never in the engine code.")
    print("==================================================")
