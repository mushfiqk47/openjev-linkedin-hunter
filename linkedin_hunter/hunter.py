"""Main CLI entrypoint for LinkedIn Job Hunter."""

import argparse
import sys
from .config import (
    DEFAULT_QUERIES,
    DEFAULT_MIN_SCORE,
    DEFAULT_MIN_MATCHES,
    DEFAULT_MAX_PAGES_PER_QUERY,
    DEFAULT_JOB_LIMIT,
)
from .cv_loader import load_cv_data
from .evaluator import JobEvaluator
from .browser import LinkedInBrowser
from .storage import (
    JobStore,
    load_seen_state,
    save_searched_query,
)


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
        default=80,
        help="Safety ceiling of scrolls on the LinkedIn feed (default: 80)",
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
        help="Max LLM evaluations per run (safety cap, default: 80)",
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

    # 1. Load Candidate Profile
    try:
        cv = load_cv_data()
        name = cv.get("basics", {}).get("name", "Mushfiq Kabir")
        print(f"[✓] Candidate Loaded: {name}")
    except Exception as e:
        print(f"[✗] Failed to load CV: {e}")
        sys.exit(1)

    # 2. Initialize Evaluator & Storage
    evaluator = JobEvaluator()
    store = JobStore()
    seen_state = load_seen_state()
    print(f"[✓] Connected to local evaluator (LM Studio: {evaluator.model})")
    print(f"[✓] Memory: {len(seen_state['seen_ids'])} job IDs, {len(seen_state['seen_signatures'])} signatures, {len(seen_state['searched_queries'])} queries recorded")

    # 3. Build query rotation queue
    queries = [args.query]
    if args.rotate_queries:
        for q in DEFAULT_QUERIES:
            if q.lower() != args.query.lower():
                queries.append(q)

    # 4. Start Browser
    browser = LinkedInBrowser(headless=args.headless)
    matched_count = 0
    evaluated_count = 0

    try:
        browser.start()
        print(f"\n[*] Hunting for at least {args.min_matches} matching job posts...")

        if args.feed_only:
            # DIRECT FEED MODE
            print(f"\n[📰] Direct Feed Mode: Navigating straight to LinkedIn News Feed...")
            matched_count = browser.browse_feed_and_find_matches(
                evaluator=evaluator,
                store=store,
                seen_state=seen_state,
                target_matches=args.min_matches,
                current_matched=matched_count,
                max_scrolls=args.max_feed_scrolls,
                view_profiles=args.view_profiles,
                criteria=getattr(args, "criteria", None),
            )
        else:
            # STEP 1: Search Job Pages across rotated queries
            for q_idx, current_query in enumerate(queries):
                if matched_count >= args.min_matches or evaluated_count >= args.limit:
                    break

                # Prevent searching the exact same query repeatedly
                q_norm = current_query.strip().lower()
                if q_norm in seen_state["searched_queries"] and q_idx > 0:
                    print(f"\n[↻] Query '{current_query}' was already searched in previous runs — skipping to avoid duplicates.")
                    continue
                save_searched_query(current_query, seen_state)

                print(f"\n" + "-" * 60)
                print(f"🔎 Query {q_idx + 1}/{len(queries)}: '{current_query}'")
                print(f"   Matches so far: {matched_count} / {args.min_matches}")
                print("-" * 60)

                for raw_job in browser.search_jobs(
                    keywords=current_query,
                    location=args.location,
                    recency=args.recency,
                    work_type=args.work_type,
                    limit=min(args.limit - evaluated_count, args.daily_cap - evaluated_count),
                    max_pages=args.max_pages,
                    seen_state=seen_state,
                    save_on_linkedin=args.save_on_linkedin,
                    view_profiles=args.view_profiles,
                    easy_apply=args.easy_apply,
                ):
                    if evaluated_count >= args.daily_cap:
                        print(f"  [!] Daily cap {args.daily_cap} reached — stopping evaluations.")
                        break
                    evaluated_count += 1
                    job_id = raw_job["job_id"]
                    title = raw_job["title"]
                    company = raw_job["company"]

                    print(f"\n[{evaluated_count}] Evaluating: {title} @ {company}...")

                    # Run SemIf logprob decision evaluation
                    eval_res = evaluator.evaluate(
                        job_title=title,
                        company=company,
                        job_description=raw_job["description"],
                        criteria=getattr(args, "criteria", None),
                    )

                    score = eval_res["match_score"]
                    fit = eval_res["fit_level"]
                    reason = eval_res["reason"]
                    extra = ""
                    if eval_res.get("low_margin"):
                        extra = " [low-margin — review manually]"
                    if eval_res.get("prescreen"):
                        extra = " [prescreen]"

                    badge = "🟢" if score >= 80 else ("🟡" if score >= 65 else "⚪")
                    print(f"    {badge} Fit Score: {score}% ({fit}){extra}")
                    print(f"    ↳ {reason}")
                    if eval_res.get("jd_keywords"):
                        print(f"    ↳ keywords: {', '.join(eval_res['jd_keywords'][:6])}")

                    # If score meets threshold, save to report
                    if score >= args.min_score:
                        matched_count += 1
                        job_record = {
                            **raw_job,
                            **eval_res,
                        }
                        store.save_job(job_record)
                        print(f"    [★ MATCH {matched_count}/{args.min_matches}] Saved to {store.md_file.name}!")

                        if matched_count >= args.min_matches:
                            print(f"\n🎯 Target reached! Found {matched_count} matching job posts.")
                            break

                if matched_count >= args.min_matches:
                    break

            # STEP 2: Fallback to LinkedIn Feed if target matches not reached
            if matched_count < args.min_matches:
                print(f"\n" + "=" * 68)
                print(f"[*] Found {matched_count}/{args.min_matches} matches from job search pages.")
                print(f"[*] Seamlessly transitioning to LinkedIn News Feed...")
                print(f"[*] Scrolling feed until all {args.min_matches} required matches are found!")
                print("=" * 68)
                matched_count = browser.browse_feed_and_find_matches(
                    evaluator=evaluator,
                    store=store,
                    seen_state=seen_state,
                    target_matches=args.min_matches,
                    current_matched=matched_count,
                    max_scrolls=args.max_feed_scrolls,
                    view_profiles=args.view_profiles,
                    criteria=getattr(args, "criteria", None),
                )

        print("\n" + "=" * 68)
        print("🎉 Hunt Complete!")
        print(f"   Evaluated:       {evaluated_count} postings & feed updates")
        print(f"   Matched Target:  {matched_count} / {args.min_matches} opportunities saved")
        print(f"   Report:          {store.md_file}")
        print(f"   Data:            {store.json_file}")
        print("=" * 68 + "\n")

    except KeyboardInterrupt:
        print("\n[!] Run stopped by user.")
    finally:
        browser.close()


if __name__ == "__main__":
    main()
