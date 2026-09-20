# Hosted models / LM Studio

The `remote` backend scores decisions through an OpenAI-compatible
`/chat/completions` server instead of loading weights locally. Point it at
LM Studio, Ollama, vLLM, or any server that returns `logprobs` with
`top_logprobs`. No GPU is required locally and no model is downloaded.

## LM Studio setup

1. Load a model in LM Studio (e.g. Qwen3.5 4B).
2. Start the local server (default `http://localhost:1234/v1`).
3. Put the connection in the env file (never on the command line):

```bash
cp .env.example .env
# edit SEMIF_REMOTE_MODEL to the loaded LM Studio model
```

4. Score the owned examples — no model flags needed:

```bash
pip install -e '.[test]'

semif-score --backend remote --mode direct \
  --input examples/decisions.jsonl \
  --output results-remote-direct.jsonl
```

The scorer reads `./.env` automatically (or `--env-file PATH` for another
file). Explicit flags remain as per-run overrides and win over the file:
`--remote-model` / `--model`, `--revision`, `--remote-base-url`,
`--remote-api-key`, `--remote-timeout`, `--remote-top-logprobs`.

| Env key | Meaning | Default |
|---|---|---|
| `SEMIF_REMOTE_BASE_URL` | OpenAI-compatible base URL | `http://localhost:1234/v1` |
| `SEMIF_REMOTE_MODEL` | Server-side model ID | (required) |
| `SEMIF_REMOTE_REVISION` | Free-form provenance label | (required) |
| `SEMIF_REMOTE_API_KEY` | Bearer token | `lm-studio` |
| `SEMIF_REMOTE_TIMEOUT` | Seconds per decision | `120` |
| `SEMIF_REMOTE_TOP_LOGPROBS` | Top logprobs per decision, 2-20 | `20` |
| `SEMIF_REMOTE_REASONING_EFFORT` | Reasoning effort for thinking models (`none` recommended for Qwen3.5; empty omits it) | `none` |

`.env` is gitignored; only `.env.example` is committed. Keep secrets out of
shell history by leaving `--remote-api-key` unset and using the file.

## Local UI

`semif-ui` serves a dependency-free page (no CDN, works offline) that scores
one decision at a time through the same backend:

```bash
semif-ui --port 8080  # open http://127.0.0.1:8080
```

It reads the model from the env file (`--env-file PATH` for another file)
and exposes `POST /api/score` taking `{state, question, options}` where each
option is a description string or an `{id, description}` object.

`--mode serial` reuses consecutive identical states (the host server owns
KV-cache reuse; `cache_hit` is reported but no local cache is kept).
`--mode shared` requires one exact state across all rows and scores them
sequentially. `--mode reranker` is rejected; reranker scoring requires the
Torch backend.

Useful flags: `--remote-timeout` (seconds per decision),
`--remote-top-logprobs` (2-20, default 20).

## How it works

The client sends the same frozen `direct_messages` prompt as the native
backend (`system` + JSON `evidence/criterion/options`, reply with one
uppercase letter), requests one token with `logprobs: true` and
`top_logprobs: N`, extracts one logprob per option letter (leading-space
and single-byte tokens accepted), and applies a softmax over only the
declared options. Prompt hash uses `direct-remote-options-v1`.

## Limitations

- The server applies its own chat template and tokenizer, so remote numbers
  are **not** comparable to the pinned native BF16 headline results.
- The server must have a model loaded (`lms ps` should list it); an empty
  server answers `/v1/models` but refuses completions.
- Thinking models (Qwen3.5) need `reasoning_effort: none`, otherwise the
  single answer token is spent on thinking and no logprobs come back. The
  client sends it by default; leave `SEMIF_REMOTE_REASONING_EFFORT` empty if
  your server rejects the parameter.
- The server must return `choices[0].logprobs.content[0].top_logprobs`
  covering every option letter. If letters are missing (merged answer token,
  disabled logprobs, truncated list), scoring fails loudly rather than
  guessing.
- Scores are conditional on the supplied options and uncalibrated, same as
  native readouts.
- Input-token limits (`--max-tokens`) are enforced server-side; the client
  does not truncate.
