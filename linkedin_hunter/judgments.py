"""Atomic model judgments over the local SemIf (LM Studio) path.

Every helper here answers a yes/no decision, a small ranking, or a
classification using the same 2-16 option logprob readout the rest of the
project already uses. No generated text, no JSON parsing, no timeouts.

The Interface is deliberately tiny (:class:`Judge`) so both the evaluator and
the apply-triage agent can sit on one seam and tests can inject a fake client.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .config import FACTOR_WEIGHTS, LLM_BASE_URL, LLM_MODEL, PROJECT_ROOT

# Reuse the backend SemIf engine exactly as the evaluator does.
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))
from semif_phase1.remote import load_model, score  # noqa: E402

# One criterion per fit axis. Each becomes a two-option (yes/no) readout.
AXIS_QUESTIONS = {
    "role_fit": (
        "Does the role itself focus on UI/UX, product, or visual interface/Figma "
        "design as its core responsibility?"
    ),
    "tools_fit": (
        "Does this posting require hands-on Figma, wireframing, prototyping, "
        "design systems, or component libraries?"
    ),
    "level_fit": (
        "Is the required seniority a good fit for roughly 1-5 years of hands-on "
        "design experience, rather than 8+ years executive/director leadership, "
        "heavy full-stack coding, or an internship?"
    ),
    "domain_fit": (
        "Is the product or team domain aligned with SaaS, web apps, mobile apps, "
        "platforms, or dashboards?"
    ),
}

AXIS_ORDER = tuple(AXIS_QUESTIONS)


@dataclass
class Readout:
    """One logprob readout: option probabilities plus timing and raw engine fields."""

    option_ids: list[str]
    probabilities: list[float]
    seconds: float
    raw: dict

    def argmax(self) -> tuple[str, float]:
        index = max(range(len(self.probabilities)), key=self.probabilities.__getitem__)
        return self.option_ids[index], self.probabilities[index]

    def top(self) -> tuple[str, float]:
        return self.argmax()

    def ranked(self) -> list[tuple[str, float]]:
        order = sorted(range(len(self.probabilities)), key=self.probabilities.__getitem__, reverse=True)
        return [(self.option_ids[i], self.probabilities[i]) for i in order]


class Judge:
    """Small Interface over the hosted SemIf scorer for atomic judgments.

    ``client``/``meta`` are injectable so tests never touch LM Studio; without
    them the same ``load_model`` default the evaluator uses is applied.
    """

    def __init__(self, base_url: str = LLM_BASE_URL, model: str = LLM_MODEL,
                 client=None, meta: dict | None = None):
        self.model = model
        self.base_url = base_url
        self.calls = 0
        if client is not None:
            self.client = client
            self.meta = meta or {"source": model, "backend": "injected"}
        else:
            self.client, _, self.meta = load_model(
                source=self.model,
                revision="lm-studio-local",
                base_url=self.base_url,
                reasoning_effort="none",
            )

    def readout(self, row: dict) -> Readout:
        """Score one full decision row (id/state/question/options)."""
        res = score(self.client, None, row, self.meta)
        self.calls += 1
        return Readout(
            option_ids=[str(i) for i in res["option_ids"]],
            probabilities=[float(p) for p in res["probabilities"]],
            seconds=float(res["forward_seconds"]),
            raw=res,
        )

    def judge(self, question: str, state: str, options: list[tuple[str, str]],
              row_id: str = "judgment") -> Readout:
        """Score an ad-hoc question with ordered ``(id, description)`` options."""
        row = {
            "id": str(row_id),
            "state": state,
            "question": question,
            "options": [{"id": str(oid), "description": str(desc)} for oid, desc in options],
        }
        return self.readout(row)

    def binary(self, question: str, state: str, yes_description: str,
               no_description: str, row_id: str = "binary") -> tuple[float, float]:
        """Return ``(P(yes), forward_seconds)`` for a two-option decision."""
        result = self.judge(question, state, [("yes", yes_description), ("no", no_description)], row_id)
        return result.probabilities[0], result.seconds

    def classify(self, question: str, state: str, labels: dict[str, str],
                 row_id: str = "classify") -> tuple[str, float, float]:
        """Return the argmax ``(label, probability, forward_seconds)`` of a closed set."""
        result = self.judge(question, state, list(labels.items()), row_id)
        label, probability = result.argmax()
        return label, probability, result.seconds

    def rank(self, question: str, state: str, options: list[tuple[str, str]],
             row_id: str = "rank") -> tuple[list[tuple[str, float]], float]:
        """Return ``([(id, probability) ...] best-first, forward_seconds)``."""
        result = self.judge(question, state, options, row_id)
        return result.ranked(), result.seconds

    def axis_scores(self, state: str, row_id: str = "axes") -> tuple[dict[str, int], float]:
        """Score role/tools/level/domain as independent yes/no readouts (0-100)."""
        scores: dict[str, int] = {}
        seconds = 0.0
        for axis in AXIS_ORDER:
            probability, elapsed = self.binary(
                AXIS_QUESTIONS[axis], state, "Yes, clearly.", "No, not really.",
                row_id=f"{row_id}-{axis}",
            )
            scores[axis] = int(round(probability * 100))
            seconds += elapsed
        return scores, seconds


def weighted_axes(axes: dict) -> int:
    """Blend axis scores with the configured factor weights into one 0-100 hint."""
    return int(round(sum(axes.get(key, 0) * FACTOR_WEIGHTS[key] for key in FACTOR_WEIGHTS)))
