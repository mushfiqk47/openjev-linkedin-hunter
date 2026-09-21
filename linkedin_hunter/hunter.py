import argparse
import sys
from .config import (
    DEFAULT_MIN_SCORE,
    DEFAULT_MIN_MATCHES,
    DEFAULT_MAX_PAGES_PER_QUERY,
    MAX_FEED_SCROLLS,
)
from .cv_loader import load_cv_data
from .evaluator import JobEvaluator
from .browser import LinkedInBrowser
from .hunt_core import HuntDeps, HuntHooks, HuntParams, run_hunt
from .storage import JobStore, load_seen_state

def main():
    parser = argparse.ArgumentParser(
        description="🎯 Automated Goal-Oriented LinkedIn Job Hunter & CV Matcher for Mushfiq Kabir"
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        default="UI/UX Designer",
        help="Initial search query for LinkedIn (default: 'UI/UX Designer')",
    )
    parser.add_argument(
        "--min-matches",
        "-m",
        "-n",
        type=int,
        default=DEFAULT_MIN_MATCHES,
        help=f"Target minimum matched jobs to discover before stopping (default: {DEFAULT_MIN_MATCHES})",
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
        help="Work type filter (default: 'all' - avoids restrictive filtering)",
    )
    parser.add_argument(
        "--min-score",
        "-s",
        type=int,
        default=DEFAULT_MIN_SCORE,
        help=f"Minimum match score to qualify (default: {DEFAULT_MIN_SCORE}%%)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES_PER_QUERY,
        help=f"Max search pages to paginate per query (default: {DEFAULT_MAX_PAGES_PER_QUERY})",
    )
    parser.add_argument(
        "--limit",
        "--max-eval",
        type=int,
        default=120,
        help="Safety ceiling of total raw jobs to evaluate across all queries (default: 120)",
    )
    parser.add_argument(
        "--max-feed-scrolls",
        type=int,
        default=MAX_FEED_SCROLLS,
        help=f"Safety ceiling of scrolls on the LinkedIn feed (default: {MAX_FEED_SCROLLS})",
    )
    parser.add_argument(
        "--rotate-queries",
        action="store_true",
        default=True,
        help="Automatically rotate to related design queries if target count is not yet reached (default: True)",
    )
    parser.add_argument(
        "--view-profiles",
        action="store_true",
        default=True,
        help="Visit recruiter and company profiles to gather details (default: True)",
    )
    parser.add_argument(
        "--save-on-linkedin",
        action="store_true",
        help="Also click 'Save' on LinkedIn for matching jobs",
    )
    parser.add_argument(
        "--feed-only",
        action="store_true",
        help="Scan LinkedIn News Feed directly for hiring leads without searching job posts first",
    )
    parser.add_argument(
        "--easy-apply",
        action="store_true",
        help="Only show Easy Apply jobs (f_AL=true, sorted by recent)",
    )
    parser.add_argument(
        "--criteria",
        nargs="*",
        default=None,
        help="Custom SemIf criteria lines (overrides dashboard/CV defaults)",
    )
    parser.add_argument(
        "--daily-cap",
        type=int,
        default=80,
        help="Max LLM evaluations per run (soft cap; only enforced with --enforce-caps)",
    )
    parser.add_argument(
        "--enforce-caps",
        action="store_true",
        help="Restore the old early-stop at --daily-cap/--limit (default: exhaustive triage of every page and feed post)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in background headless mode (default: False)",
    )

    args = parser.parse_args()

    print("=" * 68)
    print("🚀 Starting Goal-Oriented LinkedIn Job Hunter")
    print(f"   🎯 Target Goal:     Minimum {args.min_matches} qualifying matches")
    if args.feed_only:
        print("   Mode:               DIRECT FEED SCAN (LinkedIn News Feed)")
    else:
        print(f"   Query:              {args.query}")
        print(f"   Work Type:          {args.work_type.capitalize()} (No restrictive filter)")
    print(f"   Min Match Score:    {args.min_score}%")
    print(f"   Max Pages / Query:  {args.max_pages}")
    print("=" * 68)

    try:
        cv = load_cv_data()
        name = cv.get("basics", {}).get("name", "Mushfiq Kabir")
        print(f"[✓] Candidate Loaded: {name}")
    except Exception as e:
        print(f"[✗] Failed to load CV: {e}")
        sys.exit(1)

    evaluator = JobEvaluator()
    store = JobStore()
    seen_state = load_seen_state()
    print(f"[✓] Connected to local evaluator (LM Studio: {evaluator.model})")
    print(f"[✓] Memory: {len(seen_state['seen_ids'])} job IDs, {len(seen_state['seen_signatures'])} signatures, {len(seen_state['searched_queries'])} queries recorded")

    params = HuntParams(
        query=args.query, location=args.location, recency=args.recency,
        work_type=args.work_type, min_matches=args.min_matches, min_score=args.min_score,
        max_pages=args.max_pages, limit=args.limit, daily_cap=args.daily_cap,
        auto_rotate=args.rotate_queries, view_profiles=args.view_profiles,
        save_on_linkedin=args.save_on_linkedin, easy_apply=args.easy_apply,
        explore_feed=True, feed_only=args.feed_only,
        max_feed_scrolls=args.max_feed_scrolls, criteria=getattr(args, "criteria", None),
        enforce_caps=args.enforce_caps,
    )

    def _log(msg: str, level: str = "info"):
        tag = {"match": "[★]", "success": "[✓]", "warning": "[!]"}.get(level, "[i]")
        print(f"  {tag} {msg}")

    browser = LinkedInBrowser(headless=args.headless)

    try:
        browser.start()
        print(f"\n[*] Hunting for at least {params.min_matches} matching job posts...")
        deps = HuntDeps(
            evaluator=evaluator, store=store, seen_state=seen_state,
            search_jobs=browser.search_jobs, browse_feed=browser.browse_feed_and_find_matches,
        )
        result = run_hunt(params, deps, HuntHooks(on_event=_log))

        print("\n" + "=" * 68)
        print("🎉 Hunt Complete!")
        print(f"   Evaluated:       {result.evaluated} postings & feed updates")
        print(f"   Filtered out:    {result.skipped} (each with a recorded reason)")
        print(f"   Matched Target:  {result.matched} / {params.min_matches} opportunities saved")
        print(f"   Report:          {store.md_file}")
        print(f"   Data:            {store.json_file}")
        print("=" * 68 + "\n")

    except KeyboardInterrupt:
        print("\n[!] Run stopped by user.")
    finally:
        browser.close()

if __name__ == "__main__":
    main()
