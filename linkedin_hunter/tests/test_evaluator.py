from conftest import FakeClient, probs

from linkedin_hunter.evaluator import JobEvaluator, blend_score, choose_skip_reason

JOB = {
    "title": "Product Designer",
    "company": "Acme",
    "description": "We need a product designer with Figma and design systems for our SaaS dashboard.",
}


def make_evaluator(responses, **kwargs):
    client = FakeClient(responses)
    return JobEvaluator(client=client, meta={"backend": "injected", "source": "fake"}, **kwargs), client


def test_prescreen_spends_no_model_call():
    evaluator, client = make_evaluator([])
    result = evaluator.evaluate("Radiologist", "Clinic", "Medical imaging role")
    assert result["prescreen"] is True
    assert result["fit_level"] == "SKIP"
    assert result["skip_reason"].startswith("Pre-screen")
    assert client.seen == []  # no LLM call spent
    assert evaluator.judge.calls == 0


def test_model_axes_blend_into_fit_score():
    # 1 decision readout (save 0.9) + 4 axis readouts (all 0.9) = 5 calls.
    evaluator, client = make_evaluator([
        probs(0.9, 0.1),
        probs(0.9, 0.1), probs(0.9, 0.1), probs(0.9, 0.1), probs(0.9, 0.1),
    ])
    result = evaluator.evaluate(JOB["title"], JOB["company"], JOB["description"])
    assert evaluator.judge.calls == 5
    assert result["decision_score"] == 90
    assert result["axes_score"] == 90
    assert result["raw_score"] == 90
    assert result["match_score"] < result["raw_score"]  # calibrate compresses the top band
    assert result["fit_level"] == "STRONG_FIT"
    assert result["skip_reason"] == ""
    assert set(result["fit_breakdown"]) == {"role_fit", "tools_fit", "level_fit", "domain_fit"}


def test_skip_reason_names_the_weakest_axis():
    evaluator, _ = make_evaluator([
        probs(0.2, 0.8),   # decision: skip
        probs(0.9, 0.1),   # role strong
        probs(0.2, 0.8),   # tools weak
        probs(0.05, 0.95),  # level weakest -> seniority mismatch
        probs(0.6, 0.4),   # domain ok
    ])
    result = evaluator.evaluate(JOB["title"], JOB["company"], JOB["description"])
    assert result["fit_level"] == "SKIP"
    assert "Seniority" in result["skip_reason"]


def test_disabling_model_axes_falls_back_to_heuristics_and_one_call():
    evaluator, client = make_evaluator([probs(0.5, 0.5)], use_model_axes=False)
    result = evaluator.evaluate(JOB["title"], JOB["company"], JOB["description"])
    assert evaluator.judge.calls == 1
    assert result["axes_score"] > 0
    # Deterministic role axis keys off the title, not the model.
    assert result["fit_breakdown"]["role_fit"] >= 70


def test_blend_and_reason_helpers():
    assert blend_score(90, 90) == 90
    assert blend_score(0, 100) == 50
    assert "design role" in choose_skip_reason(
        {"role_fit": 10, "tools_fit": 90, "level_fit": 90, "domain_fit": 90}, [], "SKIP")
