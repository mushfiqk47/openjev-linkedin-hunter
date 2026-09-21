from conftest import FakeEvaluator, FakeStore

from linkedin_hunter.hunt_core import HuntDeps, HuntHooks, HuntParams, run_hunt

JOBS = [
    {"job_id": "1", "title": "A", "company": "Acme", "description": "design ui"},
    {"job_id": "2", "title": "B", "company": "Beta", "description": "design ui"},
    {"job_id": "3", "title": "C", "company": "Gamma", "description": "design ui"},
]

def make_deps(evaluator, skips):
    def search_jobs(**kwargs):
        return list(JOBS)

    return HuntDeps(
        evaluator=evaluator,
        store=FakeStore(),
        seen_state={"seen_ids": set(), "seen_signatures": set(), "seen_jd_hashes": set(),
                    "searched_queries": set(), "skip_reasons": {}},
        search_jobs=search_jobs,
        record_query=lambda q, seen: seen["searched_queries"].add(q.lower()),
        record_skip=lambda job_id, reason, seen: skips.append((job_id, reason)),
    )

def test_exhaustive_evaluates_every_yielded_job_and_reasons_skips():
    evaluator = FakeEvaluator(scores={"A": 90})
    skips = []
    deps = make_deps(evaluator, skips)
    params = HuntParams(query="UI/UX Designer", auto_rotate=False, explore_feed=False, min_matches=10)

    result = run_hunt(params, deps, HuntHooks())

    assert result.evaluated == 3
    assert result.matched == 1
    assert result.skipped == 2
    assert len(deps.store.saved) == 1
    assert all(reason for _job_id, reason in skips)
    assert {job_id for job_id, _ in skips} == {"2", "3"}

def test_enforce_caps_restores_early_stop():
    evaluator = FakeEvaluator(scores={})
    skips = []
    deps = make_deps(evaluator, skips)
    params = HuntParams(query="UI/UX Designer", auto_rotate=False, explore_feed=False,
                        min_matches=10, daily_cap=2, enforce_caps=True)

    result = run_hunt(params, deps, HuntHooks())

    assert result.evaluated == 2
    assert result.matched == 0

def test_feed_phase_passes_configured_max_scrolls():
    captured_max_scrolls = []
    def fake_browse_feed(**kwargs):
        captured_max_scrolls.append(kwargs.get("max_scrolls"))
        return 0

    evaluator = FakeEvaluator(scores={})
    deps = make_deps(evaluator, [])
    deps.browse_feed = fake_browse_feed

    params = HuntParams(query="UI/UX Designer", auto_rotate=False, explore_feed=True,
                        feed_only=True, max_feed_scrolls=42)
    run_hunt(params, deps, HuntHooks())

    assert captured_max_scrolls == [42]

def test_agent_parser_supports_max_feed_scrolls():
    from linkedin_hunter.agent import build_parser
    parser = build_parser()
    args = parser.parse_args(["--max-feed-scrolls", "55"])
    assert args.max_feed_scrolls == 55
