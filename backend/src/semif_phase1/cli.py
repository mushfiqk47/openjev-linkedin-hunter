from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .core import load_causal_model, validate_row
from .direct import score as direct_score
from .reranker import score as reranker_score
from .serial import SerialPrefixScorer
from .shared import score_shared

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("direct", "serial", "shared", "reranker"), required=True)
    parser.add_argument("--backend", choices=("torch", "remote"), default="torch")
    parser.add_argument("--remote-base-url", default=None,
                        help="OpenAI-compatible base URL (default: SEMIF_REMOTE_BASE_URL or http://localhost:1234/v1).")
    parser.add_argument("--remote-model", default=None,
                        help="Server-side model ID (default: --model or SEMIF_REMOTE_MODEL).")
    parser.add_argument("--remote-api-key", default=None,
                        help="Bearer token (default: SEMIF_REMOTE_API_KEY or 'lm-studio'). Prefer the env file.")
    parser.add_argument("--remote-timeout", type=float, default=None,
                        help="HTTP timeout in seconds per decision (default: SEMIF_REMOTE_TIMEOUT or 120).")
    parser.add_argument("--remote-top-logprobs", type=int, default=None,
                        help="Top logprobs requested per decision, 2-20 (default: SEMIF_REMOTE_TOP_LOGPROBS or 20).")
    parser.add_argument("--remote-reasoning-effort", default=None,
                        help="Reasoning effort sent to thinking models (default: SEMIF_REMOTE_REASONING_EFFORT or 'none'; "
                             "empty string omits it).")
    parser.add_argument("--env-file", type=Path, default=None,
                        help="Dotenv file with SEMIF_REMOTE_* settings (default: ./.env if present).")
    parser.add_argument("--model", required=False, default=None,
                        help="Model source; for --backend remote falls back to --remote-model/SEMIF_REMOTE_MODEL.")
    parser.add_argument("--revision", required=False, default=None,
                        help="Model revision label; for --backend remote falls back to SEMIF_REMOTE_REVISION.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args()
    if args.output.exists() or args.max_tokens < 1:
        parser.error("Output must be new and max-tokens must be positive")
    from . import remote as remote_backend

    env_file = args.env_file or Path(".env")
    if args.env_file and not env_file.exists():
        parser.error(f"Env file not found: {env_file}")
    if env_file.exists():
        remote_backend.load_dotenv(env_file)
    if args.backend == "torch" and (not args.model or not args.revision):
        parser.error("--model and --revision are required for the torch backend")
    if args.backend == "remote" and args.mode == "reranker":
        parser.error("Remote backend supports direct, serial, and shared modes; reranker requires torch")
    remote_options = (
        args.remote_base_url is not None
        or args.remote_model is not None
        or args.remote_api_key is not None
        or args.remote_timeout is not None
        or args.remote_top_logprobs is not None
        or args.remote_reasoning_effort is not None
    )
    if remote_options and args.backend != "remote":
        parser.error("Remote options require --backend remote")
    rows = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    if not rows:
        parser.error("Input is empty")
    for row in rows:
        validate_row(row)
    direct, serial, shared = direct_score, SerialPrefixScorer, score_shared
    if args.backend == "remote":
        base_url = args.remote_base_url or os.environ.get(remote_backend.ENV_BASE_URL) or remote_backend.DEFAULT_BASE_URL
        api_key = args.remote_api_key or os.environ.get(remote_backend.ENV_API_KEY) or "lm-studio"
        model_name = args.remote_model or args.model or os.environ.get(remote_backend.ENV_MODEL)
        revision = args.revision or os.environ.get(remote_backend.ENV_REVISION)
        if not model_name:
            parser.error("Remote backend needs a model: --remote-model/--model or SEMIF_REMOTE_MODEL in the env file")
        if not revision:
            parser.error("Remote backend needs a revision label: --revision or SEMIF_REMOTE_REVISION in the env file")
        try:
            timeout = (args.remote_timeout if args.remote_timeout is not None
                       else float(os.environ.get(remote_backend.ENV_TIMEOUT, remote_backend.DEFAULT_TIMEOUT_SECONDS)))
            top_logprobs = (args.remote_top_logprobs if args.remote_top_logprobs is not None
                            else int(os.environ.get(remote_backend.ENV_TOP_LOGPROBS, remote_backend.DEFAULT_TOP_LOGPROBS)))
        except ValueError:
            parser.error("SEMIF_REMOTE_TIMEOUT must be a number and SEMIF_REMOTE_TOP_LOGPROBS an integer")
        if timeout <= 0:
            parser.error("--remote-timeout must be positive")
        if not 2 <= top_logprobs <= 20:
            parser.error("--remote-top-logprobs must be in the range 2-20")
        reasoning_effort = (args.remote_reasoning_effort
                            if args.remote_reasoning_effort is not None
                            else os.environ.get(remote_backend.ENV_REASONING_EFFORT,
                                                 remote_backend.DEFAULT_REASONING_EFFORT))
        model, tokenizer, metadata = remote_backend.load_model(
            model_name,
            revision,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout,
            top_logprobs=top_logprobs,
            reasoning_effort=reasoning_effort,
        )
        direct, serial, shared = remote_backend.score, remote_backend.SerialPrefixScorer, remote_backend.score_shared
    else:
        model, tokenizer, metadata = load_causal_model(args.model, args.revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as destination:
        if args.mode == "shared":
            results, timing = shared(model, tokenizer, rows, metadata, args.max_tokens)
            for result in results:
                destination.write(json.dumps({**result, "shared_timing": timing}, allow_nan=False) + "\n")
        elif args.mode == "serial":
            scorer = serial(model, tokenizer, metadata, args.max_tokens)
            for row in rows:
                destination.write(json.dumps(scorer.score(row), allow_nan=False) + "\n")
                destination.flush()
        else:
            scorer = direct if args.mode == "direct" else reranker_score
            for row in rows:
                destination.write(json.dumps(scorer(model, tokenizer, row, metadata, args.max_tokens), allow_nan=False) + "\n")
                destination.flush()

if __name__ == "__main__":
    main()
