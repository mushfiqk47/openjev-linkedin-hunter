#!/usr/bin/env python3
"""LinkedIn Outreach Agent — the single entry point.

Usage:
    python agent.py next              # harvest a batch + send + status (the one-shot)
    python agent.py harvest           # fill data/contacts.json with unsent contacts
    python agent.py send              # message all pending contacts (safe defaults)
    python agent.py status            # quota + funnel report (refreshes progress.txt)
    python agent.py progress          # fetch total connections from LinkedIn
    python agent.py preflight         # Chrome/CDP + quota + files diagnostics
    python agent.py message           # preview the outreach message + where to edit it
    python agent.py selftest          # run the test suite (no browser needed)

Run `python agent.py <command> --help` for command-specific options.
"""
import argparse
import os
import sys
import unittest

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from outreach.config import load_env  # noqa: E402


def cmd_next(args):
    """One-shot: harvest a batch, send to it, then report status."""
    from outreach import harvest as harvest_mod
    from outreach.report import run_stats
    harvest_mod.run(top=args.top)
    if args.pause:
        import time
        print(f"\n[--pause] waiting {args.pause}s before sending (Ctrl+C to abort)...")
        time.sleep(args.pause)
    from outreach.dispatch import run as run_dispatch
    run_dispatch(limit=args.limit)
    run_stats()


def cmd_harvest(args):
    from outreach.harvest import run
    run(top=args.top, search_only=args.search_only,
        start_page=args.start_page, max_pages=args.max_pages)


def cmd_send(args):
    from outreach.dispatch import run
    run(limit=args.limit, start_idx=args.start_idx)


def cmd_status(_args):
    from outreach.report import run_stats
    run_stats()


def cmd_progress(args):
    from outreach.progress import run
    run(timeout=args.timeout)


def cmd_preflight(_args):
    from outreach.report import run_preflight
    run_preflight()


def cmd_message(_args):
    from outreach.report import run_message_preview
    run_message_preview()


def cmd_selftest(_args):
    tests = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(tests)
    sys.exit(0 if result.wasSuccessful() else 1)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="agent.py",
        description="LinkedIn Outreach Agent - harvest connections, send personalized DMs, track progress.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("next", help="harvest a batch + send + status (the one-shot flow)")
    p.add_argument("--top", type=int, default=None, help="how many contacts to harvest (default TOP_N=25)")
    p.add_argument("--limit", type=int, default=None, help="override DAILY_LIMIT for this run")
    p.add_argument("--pause", type=int, default=None, metavar="SEC",
                   help="pause SEC seconds between harvest and send (review window)")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("harvest", help="fill data/contacts.json with unsent contacts")
    p.add_argument("--top", type=int, default=None, help="target count (default TOP_N=25)")
    p.add_argument("--search-only", action="store_true",
                   help="skip the connections page; sweep People Search directly")
    p.add_argument("--start-page", type=int, default=None, help="first search page (default 1)")
    p.add_argument("--max-pages", type=int, default=None,
                   help="search page bound (default SEARCH_MAX_PAGES=50, or MAX_PAGES=10 with --search-only)")
    p.set_defaults(func=cmd_harvest)

    p = sub.add_parser("send", help="message all pending contacts (respects DAILY_LIMIT + pacing)")
    p.add_argument("--limit", type=int, default=None, help="override DAILY_LIMIT for this run")
    p.add_argument("--start-idx", type=int, default=None, help="resume offset into the pending list")
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("status", help="quota + funnel report (refreshes data/progress.txt)")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("progress", help="fetch the total connection count from LinkedIn")
    p.add_argument("--timeout", type=int, default=None, metavar="SEC",
                   help="browser-use timeout for this fetch (default BU_TIMEOUT=180)")
    p.set_defaults(func=cmd_progress)

    p = sub.add_parser("preflight", help="Chrome/CDP + quota + files diagnostics")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("message", help="preview the outreach message + where to edit it")
    p.set_defaults(func=cmd_message)

    p = sub.add_parser("selftest", help="run the test suite (no browser needed)")
    p.set_defaults(func=cmd_selftest)

    return parser


def main(argv=None):
    load_env()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
