"""Remote OpenAI-compatible scoring (LM Studio, Ollama, vLLM, ...).

Sends the same frozen direct prompt as :mod:`semif_phase1.core` to a
hosted ``/chat/completions`` endpoint and reads single-token option
logprobs instead of native logits. No answer text is retained.

LM Studio exposes this at ``http://localhost:1234/v1`` once a model is
loaded and the server is started. Any server implementing the OpenAI
chat-completions ``logprobs``/``top_logprobs`` contract works.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .core import LETTERS, digest, direct_messages, softmax, validate_row

PROMPT_VERSION = "direct-remote-options-v1"
DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_TOP_LOGPROBS = 20

#: Environment variables read for the remote backend (see `.env.example`).
ENV_BASE_URL = "SEMIF_REMOTE_BASE_URL"
ENV_MODEL = "SEMIF_REMOTE_MODEL"
ENV_API_KEY = "SEMIF_REMOTE_API_KEY"
ENV_REVISION = "SEMIF_REMOTE_REVISION"
ENV_TIMEOUT = "SEMIF_REMOTE_TIMEOUT"
ENV_TOP_LOGPROBS = "SEMIF_REMOTE_TOP_LOGPROBS"
ENV_REASONING_EFFORT = "SEMIF_REMOTE_REASONING_EFFORT"
DEFAULT_REASONING_EFFORT = "none"


def load_dotenv(path: str | Path) -> dict:
    """Load ``KEY=VALUE`` lines from a dotenv file into ``os.environ``.

    Existing environment variables are never overridden. Supports `#`
    comments, a leading ``export ``, and single/double-quoted values.
    Missing files load as empty. Stdlib only.
    """
    loaded: dict[str, str] = {}
    try:
        text = Path(path).read_text()
    except OSError:
        return loaded
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


@dataclass
class RemoteClient:
    """Minimal ``/chat/completions`` client using only the stdlib."""

    base_url: str
    model: str
    api_key: str = "lm-studio"
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    top_logprobs: int = DEFAULT_TOP_LOGPROBS
    reasoning_effort: str | None = DEFAULT_REASONING_EFFORT

    def chat(self, messages: list[dict], model: str | None = None) -> dict:
        payload = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": True,
            "top_logprobs": self.top_logprobs,
        }
        if self.reasoning_effort:
            # Thinking models (e.g. Qwen3.5) would otherwise spend the single
            # token on reasoning and return no answer logprobs.
            payload["reasoning_effort"] = self.reasoning_effort
        return _post_json(
            self.base_url.rstrip("/") + "/chat/completions",
            payload,
            self.api_key,
            self.timeout_seconds,
        )


def _post_json(url: str, payload: dict, api_key: str, timeout: float) -> dict:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception as error:
        raise RuntimeError(f"Remote scoring request to {url} failed: {error}") from error


def load_model(
    source: str,
    revision: str,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str = "lm-studio",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    top_logprobs: int = DEFAULT_TOP_LOGPROBS,
    reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
) -> tuple[RemoteClient, None, dict]:
    """Configure a remote model; weights stay on the host server.

    ``source`` is the server-side model ID (for LM Studio, the loaded
    model name). ``revision`` is a free-form label (server build, model
    file hash, ...) because remote servers do not expose git revisions.
    Nothing is downloaded and no GPU is required locally.
    """
    if not source:
        raise ValueError("Remote backend requires --model as the server-side model ID")
    if not revision:
        raise ValueError("Remote backend requires --revision as a free-form label")
    base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Remote base URL must start with http:// or https://")
    if timeout_seconds is None or timeout_seconds <= 0:
        raise ValueError("Remote timeout must be positive")
    if top_logprobs is None or not 2 <= top_logprobs <= 20:
        raise ValueError("Remote top_logprobs must be in the range 2-20")
    client = RemoteClient(
        base_url=base_url,
        model=source,
        api_key=api_key or "lm-studio",
        timeout_seconds=float(timeout_seconds),
        top_logprobs=int(top_logprobs),
        reasoning_effort=reasoning_effort or None,
    )
    metadata = {
        "source": source,
        "revision": revision,
        "backend": "remote",
        "base_url": base_url,
        "top_logprobs": int(top_logprobs),
        "reasoning_effort": reasoning_effort or None,
    }
    return client, None, metadata


def _candidate_token(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ""
    token = entry.get("token")
    if isinstance(token, str) and token:
        return token
    segments = entry.get("bytes")
    if isinstance(segments, list) and segments:
        try:
            return bytes(segments).decode("utf-8", errors="ignore")
        except (ValueError, TypeError):
            return ""
    return ""


def extract_option_logprobs(response: dict, count: int) -> list[float]:
    """Pull one logprob per answer letter from a chat-completion response."""
    letters = list(LETTERS[:count])
    try:
        choice = response["choices"][0]
        content = choice["logprobs"]["content"][0]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(
            "Remote server did not return choices[0].logprobs.content[0]; "
            "enable logprobs on the host server (LM Studio exposes them for "
            "chat completions)"
        ) from error
    entries = [content, *(content.get("top_logprobs") or [])]
    best: dict[str, float] = {}
    for entry in entries:
        token = _candidate_token(entry)
        logprob = entry.get("logprob") if isinstance(entry, dict) else None
        if not token or not isinstance(logprob, (int, float)):
            continue
        normalized = token.strip().upper()
        if len(normalized) == 1 and normalized in letters:
            if normalized not in best or logprob > best[normalized]:
                best[normalized] = float(logprob)
    missing = [letter for letter in letters if letter not in best]
    if missing:
        raise ValueError(
            f"Remote top_logprobs lacks option letters {missing}; "
            "the host tokenizer may merge the answer token or the server "
            "truncated the logprob list"
        )
    return [best[letter] for letter in letters]


def score(client: RemoteClient, tokenizer, row: dict, metadata: dict, max_tokens: int = 4096) -> dict:
    """Score one decision through the remote server (direct mode)."""
    _ = (tokenizer, max_tokens)  # remote servers enforce context limits
    validate_row(row)
    started = time.perf_counter()
    messages = direct_messages(row)
    prompt_hash = digest(json.dumps(messages, ensure_ascii=False))
    mark = time.perf_counter()
    response = client.chat(messages)
    request_seconds = time.perf_counter() - mark
    selected = extract_option_logprobs(response, len(row["options"]))
    usage = response.get("usage") if isinstance(response, dict) else None
    input_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    return {
        "id": row["id"],
        "option_ids": [option["id"] for option in row["options"]],
        "probabilities": softmax(selected),
        "option_logits": selected,
        "input_tokens": int(input_tokens) if isinstance(input_tokens, int) else 0,
        "forward_seconds": request_seconds,
        "total_seconds": time.perf_counter() - started,
        "prompt_sha256": prompt_hash,
        "prompt_version": PROMPT_VERSION,
        "model": metadata,
        "readout": "remote single-token logprobs restricted to declared answer slots; no generated text retained",
        "probability_status": "conditional option score; uncalibrated as decision confidence",
    }


class SerialPrefixScorer:
    """Sequential remote scorer; the host server owns KV-cache reuse."""

    def __init__(self, model: RemoteClient, tokenizer, metadata: dict, max_tokens: int = 4096):
        self.model = model
        self.metadata = {**metadata, "serving_config": "remote-sequential-v1"}
        self.max_tokens = max_tokens
        self.state = None

    def score(self, row: dict) -> dict:
        hit = self.state is not None and row.get("state") == self.state
        result = score(self.model, None, row, self.metadata, self.max_tokens)
        result["cache_hit"] = hit
        self.state = row["state"]
        return result


def score_shared(
    model: RemoteClient, tokenizer, rows: list[dict], metadata: dict, max_tokens: int = 4096
):
    """Score rows sharing one exact state via sequential remote calls."""
    if not rows or any(row["state"] != rows[0]["state"] for row in rows[1:]):
        raise ValueError("Shared scoring requires one nonempty exact state")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Decision IDs must be unique")
    started = time.perf_counter()
    results = [score(model, tokenizer, row, metadata, max_tokens) for row in rows]
    timing = {
        "total_seconds": time.perf_counter() - started,
        "batch_size": len(rows),
        "serving_config": "remote-sequential-v1",
    }
    return results, timing
