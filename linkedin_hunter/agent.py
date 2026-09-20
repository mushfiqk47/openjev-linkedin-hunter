#!/usr/bin/env python3

import argparse
import os
import sys
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
    venv_py = CURRENT_DIR / ".venv" / "bin" / "python"
    if venv_py.is_file() and Path(sys.executable).resolve() != venv_py.resolve():
        os.execv(str(venv_py), [str(venv_py)] + sys.argv)

from linkedin_hunter.browser import LinkedInBrowser
from linkedin_hunter.config import (
    DEFAULT_JOB_LIMIT,
    DEFAULT_MAX_PAGES_PER_QUERY,
    DEFAULT_MIN_MATCHES,
    DEFAULT_MIN_SCORE,
    DEFAULT_QUERIES,
    ENABLE_HUMAN_DELAYS,
    LLM_BASE_URL,
    LLM_MODEL,
    get_bool,
    get_int,
    get_str,
    load_env,
)
from linkedin_hunter.cv_loader import load_cv_data
from linkedin_hunter.evaluator import JobEvaluator
from linkedin_hunter.hunt_core import HuntDeps, HuntHooks, HuntParams, run_hunt
from linkedin_hunter.storage import JobStore, load_seen_state

def build_parser():
    parser = argparse.ArgumentParser(
        prog="agent.py",
        description="🎯 Autonomous LinkedIn Job Hunter Agent — SemIf AI Decision Pipeline",
    )
    parser.add_argument(
        "--min-matches",
        "-m",
        "-n",
        type=int,
        default=None,
        help=f"Target minimum matched jobs to find before stopping (default: from .env or {DEFAULT_MIN_MATCHES})",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        default=None,
        help=f"Initial search query (default: from .env or '{DEFAULT_QUERIES[0]}')",
    )
    parser.add_argument(
        "--location",
        "-l",
        type=str,
        default="",
        help="Search location (default: empty / candidate network)",
    )
    parser.add_argument(
        "--recency",
        "-r",
        choices=["24h", "week", "any"],
        default="week",
        help="Job posting recency (default: 'week')",
    )
    parser.add_argument(
        "--work-type",
        "-w",
        choices=["all", "remote", "on_site", "hybrid"],
        default="all",
        help="Work type filter (default: 'all')",
    )
    parser.add_argument(
        "--min-score",
        "-s",
        type=int,
        default=None,
        help=f"Minimum match score to qualify (default: from .env or {DEFAULT_MIN_SCORE}%%)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=f"Max search pages to paginate per query (default: from .env or {DEFAULT_MAX_PAGES_PER_QUERY})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"Safety limit of jobs to inspect per query (default: from .env or {DEFAULT_JOB_LIMIT})",
    )
    parser.add_argument(
        "--feed-only",
        action="store_true",
        help="Scan LinkedIn News Feed directly for hiring leads without searching job posts first",
    )
    parser.add_argument(
        "--easy-apply",
        action="store_true",
        help="Only show Easy Apply jobs",
    )
    parser.add_argument(
        "--save-on-linkedin",
        action="store_true",
        help="Also click 'Save' on LinkedIn for matching jobs",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in background headless mode (default: False)",
    )
    parser.add_argument(
        "--enforce-caps",
        action="store_true",
        help="Enforce strict daily evaluation cap (default: exhaustive evaluation)",
    )
    return parser

def main(argv=None):
    load_env()
    args = build_parser().parse_args(argv)

    target_matches = args.min_matches if args.min_matches is not None else get_int("DAILY_TARGET_MATCHES", get_int("DEFAULT_MIN_MATCHES", 10))
    min_score = args.min_score if args.min_score is not None else get_int("DEFAULT_MIN_SCORE", 70)
    query = args.query if args.query is not None else (DEFAULT_QUERIES[0] if DEFAULT_QUERIES else "UI/UX Designer")
    max_pages = args.max_pages if args.max_pages is not None else get_int("DEFAULT_MAX_PAGES_PER_QUERY", 2)
    job_limit = args.limit if args.limit is not None else get_int("DEFAULT_JOB_LIMIT", 50)
    daily_cap = get_int("DAILY_EVALUATE_CAP", 120)

    target_src = "CLI override" if args.min_matches is not None else ("from .env" if "DAILY_TARGET_MATCHES" in os.environ or "DEFAULT_MIN_MATCHES" in os.environ else "default")
    score_src = "CLI override" if args.min_score is not None else ("from .env" if "DEFAULT_MIN_SCORE" in os.environ else "default")

    print("=" * 68)
    print("🚀 Starting Autonomous LinkedIn Job Hunter Agent (Jev System)")
    print(f"   Target Matches:     {target_matches} opportunities ({target_src})")
    print(f"   Min Match Score:    {min_score}% ({score_src})")
    if args.feed_only:
        print("   Mode:               DIRECT FEED SCAN (Hiring posts)")
    else:
        print(f"   Search Query:       '{query}' ({args.work_type.capitalize()})")
        print(f"   Max Pages / Query:  {max_pages}")
    print(f"   Delays:             {'Human Jitter' if ENABLE_HUMAN_DELAYS else 'ZERO-DELAY (Max Speed)'}")
    print(f"   SemIf Backend:      {LLM_MODEL} ({LLM_BASE_URL})")
    print("=" * 68)

    try:
        cv = load_cv_data()
        name = cv.get("basics", {}).get("name", "Mushfiq Kabir")
        print(f"  [✓] Candidate Profile Loaded: {name}")
    except Exception as e:
        print(f"  [✗] Failed to load candidate CV: {e}")
        return 1

    evaluator = JobEvaluator()
    store = JobStore()
    seen_state = load_seen_state()
    print(f"  [✓] Evaluator Connected (LM Studio / SemIf model: {evaluator.model})")
    print(f"  [✓] Memory Tracked: {len(seen_state['seen_ids'])} job IDs, {len(seen_state['seen_signatures'])} signatures")

    params = HuntParams(
        query=query,
        location=args.location,
        recency=args.recency,
        work_type=args.work_type,
        min_matches=target_matches,
        min_score=min_score,
        max_pages=max_pages,
        limit=job_limit,
        daily_cap=daily_cap,
        auto_rotate=True,
        view_profiles=True,
        save_on_linkedin=args.save_on_linkedin,
        easy_apply=args.easy_apply,
        explore_feed=True,
        feed_only=args.feed_only,
        max_feed_scrolls=80,
        enforce_caps=args.enforce_caps,
    )

    def _log(msg: str, level: str = "info"):
        tag = {"match": "[★]", "success": "[✓]", "warning": "[!]", "error": "[✗]"}.get(level, "[i]")
        print(f"  {tag} {msg}")

    browser = LinkedInBrowser(headless=args.headless)
    try:
        browser.start()
        print(f"\n[*] Hunting for at least {params.min_matches} matching opportunities...")
        deps = HuntDeps(
            evaluator=evaluator,
            store=store,
            seen_state=seen_state,
            search_jobs=browser.search_jobs,
            browse_feed=browser.browse_feed_and_find_matches,
        )
        result = run_hunt(params, deps, HuntHooks(on_event=_log))

        print("\n" + "=" * 68)
        print("🎉 Hunt Complete!")
        print(f"   Evaluated:       {result.evaluated} postings & updates")
        print(f"   Filtered out:    {result.skipped} non-matching jobs")
        print(f"   Matched Target:  {result.matched} / {params.min_matches} opportunities saved")
        print(f"   Report:          {store.md_file}")
        print(f"   Data:            {store.json_file}")
        print(f"   CSV:             {store.csv_file}")
        print("=" * 68 + "\n")
        return 0
    except KeyboardInterrupt:
        print("\n[!] Job hunter stopped by user.")
        return 0
    finally:
        browser.close()

if __name__ == "__main__":
    sys.exit(main() or 0)
