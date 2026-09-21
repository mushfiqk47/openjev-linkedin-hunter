#!/usr/bin/env python3

import argparse
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    import playwright
except ImportError:
    venv_py = PROJECT_ROOT / "linkedin_hunter" / ".venv" / "bin" / "python"
    if __name__ == "__main__" and venv_py.is_file() and Path(sys.executable).resolve() != venv_py.resolve():
        os.execv(str(venv_py), [str(venv_py)] + sys.argv)

from linkedin_connect.browser import ConnectBrowser
from linkedin_connect.config import (
    DAILY_CONNECT_LIMIT,
    DRY_RUN,
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_PAGES_PER_QUERY,
    MIN_CONNECT_SCORE,
    TARGET_QUERIES,
    get_int,
    load_env,
)
from linkedin_connect.evaluator import ProfileEvaluator
from linkedin_connect.ledger import get_ledger

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent.py",
        description="🤝 Autonomous LinkedIn Targeted Connection Request Agent — SemIf AI Decision Pipeline",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help=f"Daily safety limit of connection requests to send (default: from .env or {DAILY_CONNECT_LIMIT})",
    )
    parser.add_argument(
        "--min-score",
        "-s",
        type=int,
        default=None,
        help=f"Minimum AI match score (0-100) required to send request (default: from .env or {MIN_CONNECT_SCORE})",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        default=None,
        help="Search query to run (default: rotates through TARGET_QUERIES)",
    )
    parser.add_argument(
        "--max-pages",
        "-p",
        type=int,
        default=None,
        help=f"Maximum pages to scan per query (default: from .env or {MAX_PAGES_PER_QUERY})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate evaluation without clicking 'Connect' or sending requests",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in background headless mode (default: False)",
    )
    return parser

def main(argv=None) -> int:
    load_env()
    args = build_parser().parse_args(argv)

    daily_limit = args.limit if args.limit is not None else get_int("DAILY_CONNECT_LIMIT", DAILY_CONNECT_LIMIT)
    min_score = args.min_score if args.min_score is not None else get_int("MIN_CONNECT_SCORE", MIN_CONNECT_SCORE)
    max_pages = args.max_pages if args.max_pages is not None else get_int("MAX_PAGES_PER_QUERY", MAX_PAGES_PER_QUERY)
    dry_run = args.dry_run or DRY_RUN

    queries = [args.query] if args.query else TARGET_QUERIES

    ledger = get_ledger()
    today_sent = ledger.get_today_sent_count()
    remaining_budget = max(0, daily_limit - today_sent)

    limit_src = "CLI override" if args.limit is not None else ("from .env" if "DAILY_CONNECT_LIMIT" in os.environ else "default")
    score_src = "CLI override" if args.min_score is not None else ("from .env" if "MIN_CONNECT_SCORE" in os.environ else "default")

    print("=" * 68)
    print("🚀 Starting Autonomous LinkedIn Targeted Connection Agent (Jev System)")
    print(f"   Daily Safety Cap:    {daily_limit} requests ({limit_src})")
    print(f"   Sent Today:          {today_sent} requests")
    print(f"   Remaining Budget:    {remaining_budget} requests")
    print(f"   Min Match Score:     {min_score}% ({score_src})")
    print(f"   Target Archetypes:   Design Leaders, Tech Recruiters, Startup Founders")
    print(f"   Strategy:            Blank Connection Request (Highest Acceptance Rate)")
    print(f"   Mode:                {'DRY-RUN SIMULATION (No Requests Sent)' if dry_run else 'LIVE DISPATCH'}")
    print(f"   SemIf Backend:       {LLM_MODEL} ({LLM_BASE_URL})")
    print("=" * 68)

    if remaining_budget <= 0 and not dry_run:
        print("\n[✓] Daily connection budget already reached for today! Halting to protect LinkedIn account.")
        return 0

    evaluator = ProfileEvaluator()
    browser = ConnectBrowser(headless=args.headless)

    total_evaluated = 0
    total_qualified = 0
    total_sent = 0
    total_skipped = 0
    total_restricted = 0

    try:
        browser.start()
        print(f"\n[*] Starting discovery across {len(queries)} target query categories...")

        for q_idx, query in enumerate(queries, 1):
            if remaining_budget <= 0 and not dry_run:
                print("\n[✓] Daily connection budget reached. Halting gracefully.")
                break

            print(f"\n[{q_idx}/{len(queries)}] Query Category: '{query}'")

            for page in range(1, max_pages + 1):
                if remaining_budget <= 0 and not dry_run:
                    break

                cards = browser.navigate_search(query, page)
                if not cards:
                    print(f"  [i] No more candidate cards found on page {page}.")
                    break

                print(f"  [i] Page {page}: Discovered {len(cards)} candidate profiles.")

                for card in cards:
                    if remaining_budget <= 0 and not dry_run:
                        break

                    name = card.get("name", "").strip()
                    headline = card.get("headline", "").strip()
                    location = card.get("location", "").strip()
                    url = card.get("profile_url", "").strip()
                    btn_type = card.get("button_type", "unknown")

                    if not name or not url:
                        continue

                    total_evaluated += 1

                    # 1. Check if restricted
                    if ledger.is_restricted(name, url):
                        total_restricted += 1
                        ledger.record_restricted(name, url, headline)
                        print(f"  [⛔ Restricted] {name} matched blacklist in restricted.txt · Skipped")
                        continue

                    # 2. Check if already connected or in outreach ledger
                    if ledger.is_already_connected_or_messaged(url):
                        total_skipped += 1
                        print(f"  [i Already Connected] {name} is already a 1st-degree connection · Skipped")
                        continue

                    # 3. Check if handled previously
                    if ledger.is_handled(url):
                        total_skipped += 1
                        continue

                    # 4. Check button status
                    if btn_type == "pending":
                        total_skipped += 1
                        ledger.record_sent(name, url, headline, "pending", 100, reason="Existing pending request")
                        print(f"  [i Pending] Connection request to {name} already pending · Skipped")
                        continue

                    # 5. AI Evaluation
                    eval_res = evaluator.evaluate(name, headline, location)
                    archetype = eval_res.get("archetype", "general")
                    score = eval_res.get("score", 0)
                    reason = eval_res.get("reason", "")
                    qualified = eval_res.get("qualified", False)

                    if not qualified:
                        total_skipped += 1
                        ledger.record_skipped(name, url, headline, archetype, score, reason=reason)
                        print(f"  [!] Skipped: {name} | Score: {score}% ({archetype}) · {reason}")
                        continue

                    total_qualified += 1
                    print(f"  [★ Qualify] {name} | Score: {score}% [{archetype.upper()}] · {headline}")

                    # 6. Dispatch Connection Request
                    if dry_run:
                        total_sent += 1
                        remaining_budget -= 1
                        print(f"    [DRY-RUN] Would send blank connection request to {name} ({archetype})")
                    else:
                        success, detail = browser.send_connection_request(card["index"], name)
                        if success:
                            total_sent += 1
                            remaining_budget -= 1
                            ledger.record_sent(name, url, headline, archetype, score, reason=detail)
                            print(f"    [✓ Connect Sent] Blank invitation sent to {name} ({archetype})! [Remaining: {remaining_budget}]")
                        else:
                            if "weekly" in detail.lower():
                                print(f"\n[!] WARNING: {detail}!")
                                print("    Stopping agent immediately to protect account.")
                                remaining_budget = 0
                                break
                            else:
                                total_skipped += 1
                                ledger.record_skipped(name, url, headline, archetype, score, reason=detail)
                                print(f"    [!] Failed to connect: {detail}")

        print("\n" + "=" * 68)
        print("🎉 Connection Campaign Complete!")
        print(f"   Profiles Evaluated:      {total_evaluated}")
        print(f"   Qualified Prospects:     {total_qualified}")
        print(f"   Requests Dispatched:     {total_sent}")
        print(f"   Profiles Skipped:        {total_skipped}")
        print(f"   Restricted Intercepted:  {total_restricted}")
        print(f"   Remaining Daily Budget:  {remaining_budget}")
        print(f"   Registry State:          {ledger.registry_path}")
        print(f"   Human Audit Ledger:      {ledger.ledger_path}")
        print("=" * 68 + "\n")
        return 0

    except KeyboardInterrupt:
        print("\n[!] Connection agent stopped by user.")
        return 0
    finally:
        browser.close()

if __name__ == "__main__":
    sys.exit(main() or 0)
