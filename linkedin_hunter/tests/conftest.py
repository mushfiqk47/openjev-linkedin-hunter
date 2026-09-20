import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LETTERS = "ABCDEFGHIJKLMNOP"

def probs(*values: float) -> list[float]:

    return [math.log(v) for v in values]

class FakeClient:

    def __init__(self, responses=None, responder=None):
        self.responses = list(responses or [])
        self.responder = responder
        self.seen = []

    def chat(self, messages, model=None):
        self.seen.append(messages)
        payload = json.loads(messages[-1]["content"])
        count = len(payload["options"])
        if self.responder is not None:
            logprobs = list(self.responder(payload, count))
        else:
            logprobs = list(self.responses.pop(0))
        assert len(logprobs) == count, f"responder gave {len(logprobs)} logprobs for {count} options"
        return {
            "choices": [{
                "message": {"content": LETTERS[0]},
                "logprobs": {"content": [{
                    "token": LETTERS[0],
                    "logprob": logprobs[0],
                    "top_logprobs": [
                        {"token": LETTERS[i], "logprob": value}
                        for i, value in enumerate(logprobs)
                    ],
                }]},
            }],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1},
        }

class FakeEvaluator:

    def __init__(self, scores: dict | None = None, default: int = 50):
        self.scores = scores or {}
        self.default = default
        self.seen = []

    def evaluate(self, job_title, company, job_description, criteria=None):
        self.seen.append((job_title, company))
        score = int(self.scores.get(job_title, self.default))
        return {
            "match_score": score,
            "fit_level": "STRONG_FIT" if score >= 80 else ("CONSIDER" if score >= 65 else "SKIP"),
            "skip_reason": "" if score >= 65 else "Below the fit threshold.",
            "matched_skills": [],
            "missing_skills": [],
            "reason": "fake",
            "forward_seconds": 0.0,
            "prescreen": False,
        }

    def evaluate_feed_post(self, author, post_text, criteria=None):
        return self.evaluate(post_text or author, "", author)

class FakeStore:
    def __init__(self):
        self.saved = []

    def save_job(self, record):
        self.saved.append(record)
