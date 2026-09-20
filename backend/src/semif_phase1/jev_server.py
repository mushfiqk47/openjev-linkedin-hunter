"""Jev choice-contract server backed by a hosted model.

Answers the TypeSafe-shaped choice request that a Jev client sends
(``{model, state, questions}`` in, ``{model, answers, usage}`` out) through an
OpenAI-compatible server (LM Studio, Ollama, vLLM), so a Jev contract consumer
can run without the hosted API and without an API key. Every question's criteria
become SemIf options:

- 2-16 criteria: one single-token logprob readout over lettered options
  (``A``-``P``), exactly like :mod:`semif_phase1.remote`.
- More criteria (large element tables): one yes/no relevance readout per
  criterion, normalized across criteria.
- Exactly one criterion: the only candidate is answered with probability 1.0 and
  the model is not asked to rank a single option, so no call is spent on it.

The choice is always the probability argmax and probabilities sum to one, which
is what the contract's client-side validation requires. Confidence is the top
probability: a ranking signal, not calibrated confidence.

Both ``POST /v1/systemone`` (TypeSafe's path) and ``POST /v1/choices`` are
served. Stdlib-only HTTP, matching the ``remote`` backend.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import remote as remote_backend
from .core import LETTERS, digest, direct_messages, softmax, validate_row

PROMPT_VERSION = "jev-choices-remote-v1"
BINARY_PROMPT_VERSION = "jev-choices-remote-binary-v1"
SINGLE_PROMPT_VERSION = "jev-choices-single-candidate-v1"
DEFAULT_PORT = 8090
PATHS = frozenset({"/v1/systemone", "/v1/choices"})
MAX_DIRECT_OPTIONS = len(LETTERS)  # 16 single-token letter slots
BINARY_SYSTEM = "Answer the question about the candidate with only the single word yes or no."


def render_criterion(value) -> str:
    """Render a criterion (description string or target dict) as option text."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{key}: {item}" for key, item in value.items()
                         if isinstance(item, (str, int, float, bool)))
    return json.dumps(value, ensure_ascii=False)


def question_text(instructions: dict, question_id: str) -> str:
    """Use the request's own instruction text as the criterion, if it has any."""
    if isinstance(instructions, dict):
        for key in ("question", "goal"):
            value = instructions.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return question_id


def parse_request(body: dict) -> tuple[str | None, dict, dict]:
    """Validate a Jev choice request; return ``(model, state, questions)``."""
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")
    state = body.get("state")
    questions = body.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise ValueError("Request needs a nonempty questions object")
    for question_id, question in questions.items():
        if not isinstance(question, dict) or question.get("type") != "choice":
            raise ValueError(f"Question {question_id!r} must be a choice question")
        criteria = question.get("criteria")
        if not isinstance(criteria, dict) or not criteria:
            raise ValueError(f"Question {question_id!r} needs at least one criterion")
    model = body.get("model")
    return (model if isinstance(model, str) and model else None, state, questions)


def build_row(question_id: str, state, question: dict) -> tuple[dict, list[str]]:
    """Pack one Jev question into a SemIf decision row; return row and criterion keys."""
    criteria = question["criteria"]
    instructions = question.get("instructions", {})
    keys = list(criteria.keys())
    row = {
        "id": str(question_id),
        "state": {"context": state, "instructions": instructions},
        "question": question_text(instructions, str(question_id)),
        "options": [{"id": str(key), "description": render_criterion(criteria[key])} for key in keys],
    }
    # A target head may offer a single candidate; a large element table may exceed
    # the 16 lettered slots, which the binary relevance readout covers instead.
    validate_row(row, min_options=1, max_options=max(len(keys), MAX_DIRECT_OPTIONS))
    return row, [str(key) for key in keys]


def answer_single(keys: list[str]) -> dict:
    """Answer a single-candidate question without spending a model call."""
    return {
        "choice": keys[0],
        "probabilities": {keys[0]: 1.0},
        "confidence": 1.0,
        "prompt_version": SINGLE_PROMPT_VERSION,
        "model_calls": 0,
    }


def answer_direct(client, row: dict, keys: list[str], model: str | None) -> dict:
    """One lettered-option logprob readout over every criterion of the question."""
    messages = direct_messages(row)
    prompt_hash = digest(json.dumps(messages, ensure_ascii=False))
    response = client.chat(messages, model=model)
    probabilities = softmax(remote_backend.extract_option_logprobs(response, len(keys)))
    top = max(range(len(keys)), key=probabilities.__getitem__)
    return {
        "choice": keys[top],
        "probabilities": dict(zip(keys, probabilities)),
        "confidence": probabilities[top],
        "prompt_sha256": prompt_hash,
        "prompt_version": PROMPT_VERSION,
        "model_calls": 1,
    }


def extract_yes_no(response: dict) -> float:
    """Return yes-minus-no log-odds from a binary readout response."""
    try:
        content = response["choices"][0]["logprobs"]["content"][0]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("Remote server returned no logprobs for binary relevance") from error
    best: dict[str, float] = {}
    for entry in [content, *(content.get("top_logprobs") or [])]:
        token = remote_backend._candidate_token(entry)
        logprob = entry.get("logprob") if isinstance(entry, dict) else None
        if not token or not isinstance(logprob, (int, float)):
            continue
        word = token.strip().upper()
        if word in ("YES", "NO") and (word not in best or logprob > best[word]):
            best[word] = float(logprob)
    if "YES" not in best or "NO" not in best:
        raise ValueError("Remote top_logprobs lacks yes/no tokens for binary relevance")
    return best["YES"] - best["NO"]


def binary_messages(row: dict, description: str) -> list[dict]:
    return [
        {"role": "system", "content": BINARY_SYSTEM},
        {"role": "user", "content": json.dumps({
            "evidence": row["state"],
            "question": row["question"],
            "candidate": description,
        }, ensure_ascii=False)},
    ]


def answer_binary(client, row: dict, keys: list[str], model: str | None) -> dict:
    """One yes/no relevance call per criterion, for questions with many criteria."""
    odds = [extract_yes_no(client.chat(binary_messages(row, option["description"]), model=model))
            for option in row["options"]]
    probabilities = softmax(odds)
    top = max(range(len(keys)), key=probabilities.__getitem__)
    return {
        "choice": keys[top],
        "probabilities": dict(zip(keys, probabilities)),
        "confidence": probabilities[top],
        "prompt_version": BINARY_PROMPT_VERSION,
        "model_calls": len(keys),
    }


def serve_request(client, metadata: dict, body: dict) -> dict:
    """Answer every question in a Jev choice request."""
    started = time.perf_counter()
    model, state, questions = parse_request(body)
    answers, calls = {}, 0
    for question_id, question in questions.items():
        row, keys = build_row(question_id, state, question)
        if len(keys) == 1:
            answers[str(question_id)] = answer_single(keys)
        elif len(keys) <= MAX_DIRECT_OPTIONS:
            answers[str(question_id)] = answer_direct(client, row, keys, model)
        else:
            answers[str(question_id)] = answer_binary(client, row, keys, model)
        calls += answers[str(question_id)]["model_calls"]
    return {
        "model": model or metadata.get("source"),
        "answers": answers,
        "usage": {
            "questions": len(answers),
            "model_calls": calls,
            "elapsed_seconds": time.perf_counter() - started,
        },
    }


def make_handler(client, metadata: dict):
    """Build the request handler class bound to one hosted-model client."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "SemIfJevChoices/1.0"

        def _send(self, code: int, body: bytes, content_type: str):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send(200, json.dumps({
                "service": "semif-jev-choices",
                "paths": sorted(PATHS),
                "model": metadata.get("source"),
            }).encode(), "application/json")

        def do_POST(self):
            if self.path not in PATHS:
                self._send(404, b'{"error": "not found"}', "application/json")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"null")
                result = serve_request(client, metadata, body)
            except (ValueError, json.JSONDecodeError) as error:
                self._send(400, json.dumps({"error": str(error)}).encode(), "application/json")
                return
            except Exception as error:  # host unreachable, bad logprobs, ...
                self._send(502, json.dumps({"error": str(error)}).encode(), "application/json")
                return
            self._send(200, json.dumps(result, allow_nan=False).encode(), "application/json")

        def log_message(self, *args):
            pass

    return Handler


def load_configuration(env_file: Path | None = None):
    """Build the hosted-model client from ``SEMIF_REMOTE_*`` settings.

    ``env_file`` is optional so a launcher can supply its own environment first.
    """
    if env_file is not None:
        remote_backend.load_dotenv(env_file)
    import os

    model_name = os.environ.get(remote_backend.ENV_MODEL)
    if not model_name:
        raise ValueError("Set SEMIF_REMOTE_MODEL in the env file to the model the host server has loaded")
    try:
        timeout = float(os.environ.get(remote_backend.ENV_TIMEOUT, remote_backend.DEFAULT_TIMEOUT_SECONDS))
        top_logprobs = int(os.environ.get(remote_backend.ENV_TOP_LOGPROBS, remote_backend.DEFAULT_TOP_LOGPROBS))
    except ValueError as error:
        raise ValueError(
            "SEMIF_REMOTE_TIMEOUT must be a number and SEMIF_REMOTE_TOP_LOGPROBS an integer") from error
    client, _, metadata = remote_backend.load_model(
        model_name, os.environ.get(remote_backend.ENV_REVISION) or "local",
        base_url=os.environ.get(remote_backend.ENV_BASE_URL) or remote_backend.DEFAULT_BASE_URL,
        api_key=os.environ.get(remote_backend.ENV_API_KEY) or "lm-studio",
        timeout_seconds=timeout,
        top_logprobs=top_logprobs,
        reasoning_effort=os.environ.get(remote_backend.ENV_REASONING_EFFORT,
                                        remote_backend.DEFAULT_REASONING_EFFORT) or None,
    )
    return client, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Jev choice contract from a hosted model.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--env-file", type=Path, default=None,
                        help="Dotenv file with SEMIF_REMOTE_* settings (default: ./.env if present).")
    args = parser.parse_args()
    env_file = args.env_file or Path(".env")
    if args.env_file and not env_file.exists():
        parser.error(f"Env file not found: {env_file}")
    try:
        client, metadata = load_configuration(env_file if env_file.exists() else None)
    except ValueError as error:
        parser.error(str(error))
    server = ThreadingHTTPServer((args.host, args.port), make_handler(client, metadata))
    print(f"SemIf Jev choices on http://{args.host}:{args.port}/v1/systemone "
          f"(model {metadata['source']}, Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
