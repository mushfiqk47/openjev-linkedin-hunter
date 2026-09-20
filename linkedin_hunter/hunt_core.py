"""Hunting core: one deep Module behind a small Interface.

Seam: `run_hunt(params, deps, hooks)` is the single place where hunting behaviour lives.
Adapters: CLI (`hunter.py`) and Web (`web.py`) are thin adapters translating
argparse / JSON into HuntParams plus log/stop hooks. Two adapters = real seam.

Depth: query rotation, dedup, BM25-gated SemIf evaluation, JD-hash save,
feed fallback, and caps all sit behind one 3-arg function. Deletion test:
deleting this Module pushes branching, thresholds, and ordering back into
every caller. Keeping it gives Leverage to callers and Locality to maintainers.

Test surface is the Interface: fakes cross the same seam (FakeEvaluator,
iterable fake browser, in-memory store). No LM Studio or Playwright needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

from .config import DEFAULT_QUERIES, DEFAULT_MIN_SCORE, DEFAULT_MIN_MATCHES
from .storage import record_skip_reason, save_searched_query


@dataclass
class HuntParams:
    """Everything a caller must know: plain data, no behaviour."""

    query: str = "UI/UX Designer"
    location: str = ""
    recency: str = "week"
    work_type: str = "all"
    min_matches: int = DEFAULT_MIN_MATCHES
    min_score: int = DEFAULT_MIN_SCORE
    max_pages: int = 5
    limit: int = 50
    daily_cap: int = 80
    auto_rotate: bool = True
    view_profiles: bool = True
    save_on_linkedin: bool = False
    easy_apply: bool = False
    explore_feed: bool = True
    feed_only: bool = False
    max_feed_scrolls: int = 8
    criteria: list[str] | None = None
    # Feature 2: caps are soft by default so every card/feed post is evaluated and
    # reasoned about. Set True to restore the old daily_cap/limit early-stop safety.
    enforce_caps: bool = False


@dataclass
class HuntResult:
    matched: int = 0
    evaluated: int = 0
    skipped: int = 0
    saved_job_ids: list[str] = field(default_factory=list)


class Evaluator(Protocol):
    def evaluate(self, job_title: str, company: str, job_description: str,
                 criteria: list[str] | None = None) -> dict: ...
    def evaluate_feed_post(self, author: str, post_text: str,
                           criteria: list[str] | None = None) -> dict: ...


@dataclass
class HuntDeps:
    """Accepted dependencies — never created inside the Module (testability)."""

    evaluator: Evaluator
    store: object  # JobStore: save_job(record)
    seen_state: dict
    # Factory so tests inject a fake browser; prod passes LinkedInBrowser.
    search_jobs: Callable[..., Iterable[dict]]
    browse_feed: Callable[..., int] | None = None
    # Query recorder; defaults to persistent save_searched_query so tests can
    # inject a no-op and stay hermetic (no real seen_jobs.json writes).
    record_query: Callable[..., None] | None = None
    # Skip-reason recorder; same injectable pattern so tests never write
    # seen_jobs.json.
    record_skip: Callable[..., None] | None = None


@dataclass
class HuntHooks:
    on_event: Callable[[str, str], None] = lambda msg, level="info": None
    should_stop: Callable[[], bool] = lambda: False


def build_queries(initial: str, auto_rotate: bool) -> list[str]:
    queries = [initial]
    if auto_rotate:
        queries += [q for q in DEFAULT_QUERIES if q.lower() != initial.lower()]
    return queries


def run_hunt(params: HuntParams, deps: HuntDeps, hooks: HuntHooks = HuntHooks()) -> HuntResult:
    """Run the full hunt: search phase then feed fallback. Small Interface, deep Implementation."""
    result = HuntResult()
    seen = deps.seen_state

    if params.feed_only:
        hooks.on_event("Direct feed mode: scanning LinkedIn News Feed.", "info")
        result.matched = _feed_phase(params, deps, hooks, result, current_matched=0)
        return result

    cap = min(params.limit, params.daily_cap)
    for q_idx, q in enumerate(build_queries(params.query, params.auto_rotate)):
        if hooks.should_stop() or result.matched >= params.min_matches:
            break
        if params.enforce_caps and result.evaluated >= cap:
            hooks.on_event(f"Cap reached ({cap} evaluations).", "warning")
            break
        q_norm = q.strip().lower()
        if q_norm in seen.get("searched_queries", set()) and q_idx > 0:
            hooks.on_event(f"Skipping previously searched query: '{q}'", "info")
            continue
        (deps.record_query or save_searched_query)(q, seen)
        hooks.on_event(f"Searching [{q_idx + 1}]: '{q}' ({result.matched}/{params.min_matches})", "info")

        # Exhaustive triage: pass the full per-query bound unless caps are enforced.
        remaining = (cap - result.evaluated) if params.enforce_caps else params.limit
        for raw_job in deps.search_jobs(
            keywords=q, location=params.location, recency=params.recency,
            work_type=params.work_type, limit=remaining, max_pages=params.max_pages,
            seen_state=seen, save_on_linkedin=params.save_on_linkedin,
            view_profiles=params.view_profiles, easy_apply=params.easy_apply,
            stop_check=hooks.should_stop,
        ):
            if hooks.should_stop():
                break
            if params.enforce_caps and result.evaluated >= cap:
                break
            result.evaluated += 1
            title, company = raw_job.get("title", ""), raw_job.get("company", "")
            eval_res = deps.evaluator.evaluate(title, company, raw_job.get("description", ""), criteria=params.criteria)
            score = int(eval_res.get("match_score", 0))
            if eval_res.get("prescreen"):
                reason = eval_res.get("skip_reason") or "Pre-screen filtered."
                result.skipped += 1
                (deps.record_skip or record_skip_reason)(raw_job.get("job_id", ""), reason, seen)
                hooks.on_event(f"Pre-screen filtered: {title} @ {company} \u2014 {reason}", "info")
                continue
            review = " [review]" if eval_res.get("needs_review") else ""
            low = " [low-margin]" if eval_res.get("low_margin") else ""
            if score >= params.min_score:
                result.matched += 1
                deps.store.save_job({**raw_job, **eval_res})
                result.saved_job_ids.append(str(raw_job.get("job_id", "")))
                hooks.on_event(f"Match {result.matched}/{params.min_matches}: {title} @ {company} ({score}%){low}{review}", "match")
                if result.matched >= params.min_matches:
                    hooks.on_event(f"Target {params.min_matches} reached.", "success")
                    break
            else:
                result.skipped += 1
                reason = eval_res.get("skip_reason") or "Below fit threshold."
                (deps.record_skip or record_skip_reason)(raw_job.get("job_id", ""), reason, seen)
                hooks.on_event(f"Filtered out: {title} @ {company} ({score}%) \u2014 {reason}{review}", "info")
        if result.matched >= params.min_matches:
            break

    if not hooks.should_stop() and params.explore_feed and result.matched < params.min_matches and deps.browse_feed is not None:
        hooks.on_event(
            f"Search gave {result.matched}/{params.min_matches}. Falling back to feed.", "warning")
        result.matched = _feed_phase(params, deps, hooks, result, current_matched=result.matched)
    return result


def _feed_phase(params: HuntParams, deps: HuntDeps, hooks: HuntHooks,
                result: HuntResult, current_matched: int) -> int:
    if deps.browse_feed is None:
        return current_matched
    return deps.browse_feed(
        evaluator=deps.evaluator, store=deps.store, seen_state=deps.seen_state,
        target_matches=params.min_matches, current_matched=current_matched,
        max_scrolls=params.max_feed_scrolls, view_profiles=params.view_profiles,
        criteria=params.criteria,
        exhaustive=not params.enforce_caps,
        on_status_update=lambda s: hooks.on_event(s, "info"),
        stop_check=hooks.should_stop,
    )
