#!/usr/bin/env python3

import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from outreach.config import get_bool, get_int, get_str, load_env
from outreach.core import OutreachHooks, OutreachParams, run_outreach

def build_parser():
    parser = argparse.ArgumentParser(
        prog="agent.py",
        description="🎯 Autonomous LinkedIn Network Outreach Agent — SemIf Persona & Decision Engine",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Override DAILY_LIMIT for this run (default: from .env or 15)",
    )
    parser.add_argument(
        "--top",
        "-t",
        "-n",
        type=int,
        default=None,
        help="Target number of unsent contacts to ensure in pool (default: TOP_N from .env or 25)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the outreach run without typing/sending DMs or writing to the ledger",
    )
    parser.add_argument(
        "--pause",
        "-p",
        type=int,
        default=None,
        metavar="SEC",
        help="Pause SEC seconds between harvest and dispatch for review (default: from .env or 0)",
    )
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="Skip the connections page; sweep 1st-degree People Search directly",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=None,
        help="First search page (default: from .env or 1)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum search pages to sweep (default: from .env or 50)",
    )
    return parser

def main(argv=None):
    load_env()
    args = build_parser().parse_args(argv)

    daily_limit = args.limit if args.limit is not None else get_int("DAILY_LIMIT", 15)
    top_n = args.top if args.top is not None else get_int("TOP_N", 25)
    pause_sec = args.pause if args.pause is not None else (get_int("PAUSE", 0) or None)
    dry_run = args.dry_run or get_bool("DRY_RUN", False)
    search_only = args.search_only or get_bool("SEARCH_ONLY", False)
    start_page = args.start_page if args.start_page is not None else get_int("START_PAGE", 1)
    max_pages = args.max_pages if args.max_pages is not None else get_int("MAX_PAGES", get_int("SEARCH_MAX_PAGES", 50))

    limit_src = "CLI override" if args.limit is not None else ("from .env" if "DAILY_LIMIT" in os.environ else "default (15)")
    top_src = "CLI override" if args.top is not None else ("from .env" if "TOP_N" in os.environ else "default (25)")
    mode_src = "CLI flag" if args.dry_run else ("from .env" if "DRY_RUN" in os.environ else "live")

    print("=" * 68)
    print("🚀 Starting Autonomous LinkedIn Network Outreach Agent (Jev System)")
    print(f"   Target Batch:       {top_n} ({top_src})")
    print(f"   Daily Send Limit:   {daily_limit} ({limit_src})")
    print(f"   Mode:               {'DRY-RUN SIMULATION' if dry_run else 'LIVE DISPATCH'} ({mode_src})")
    if search_only:
        search_src = "CLI flag" if args.search_only else "from .env"
        print(f"   Search Sweep:       1st-degree People Search pages {start_page}..{max_pages} ({search_src})")
    if pause_sec:
        pause_src = "CLI flag" if args.pause is not None else "from .env"
        print(f"   Review Pause:       {pause_sec}s review window ({pause_src})")
    print("=" * 68)

    params = OutreachParams(
        top=top_n,
        limit=daily_limit,
        pause=pause_sec,
        dry_run=dry_run,
        search_only=search_only,
        start_page=start_page,
        max_pages=max_pages,
    )

    def _log(msg: str, level: str = "info"):
        tag = {"match": "[★]", "success": "[✓]", "warning": "[!]", "error": "[✗]"}.get(level, "[i]")
        print(f"  {tag} {msg}")

    hooks = OutreachHooks(on_event=_log)
    result = run_outreach(params, hooks)
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
