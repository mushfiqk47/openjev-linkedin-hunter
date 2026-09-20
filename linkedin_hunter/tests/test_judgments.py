import pytest
from conftest import FakeClient, probs

from linkedin_hunter.judgments import AXIS_ORDER, Judge, weighted_axes

META = {"backend": "injected", "source": "fake"}

def test_binary_returns_yes_probability_and_seconds():
    judge = Judge(client=FakeClient([probs(0.8, 0.2)]), meta=META)
    probability, seconds = judge.binary("Q?", "state", "yes desc", "no desc")
    assert probability == pytest.approx(0.8, abs=1e-3)
    assert seconds >= 0.0
    assert judge.calls == 1

def test_classify_returns_argmax_label():
    judge = Judge(client=FakeClient([probs(0.1, 0.7, 0.2)]), meta=META)
    label, probability, _ = judge.classify("Which?", "state", {"a": "A", "b": "B", "c": "C"})
    assert label == "b"
    assert probability == pytest.approx(0.7, abs=1e-3)

def test_rank_orders_options_best_first():
    judge = Judge(client=FakeClient([probs(0.2, 0.5, 0.3)]), meta=META)
    ranked, _ = judge.rank("Best?", "state", [("x", "X"), ("y", "Y"), ("z", "Z")])
    assert [option for option, _ in ranked] == ["y", "z", "x"]

def test_axis_scores_spend_one_readout_per_axis():
    responses = [probs(0.9, 0.1), probs(0.8, 0.2), probs(0.1, 0.9), probs(0.7, 0.3)]
    client = FakeClient(responses)
    judge = Judge(client=client, meta=META)
    axes, seconds = judge.axis_scores("state")
    assert set(axes) == set(AXIS_ORDER)
    assert axes["role_fit"] == 90
    assert axes["tools_fit"] == 80
    assert axes["level_fit"] == 10
    assert axes["domain_fit"] == 70
    assert judge.calls == 4
    assert seconds >= 0.0

def test_weighted_axes_uses_configured_weights():
    assert weighted_axes({"role_fit": 90, "tools_fit": 90, "level_fit": 90, "domain_fit": 90}) == 90
    assert weighted_axes({"role_fit": 100, "tools_fit": 0, "level_fit": 0, "domain_fit": 0}) == 35
