# Jev choice server

`semif-jevsrv` answers the TypeSafe-shaped choice contract — `{model, state, questions}` in,
`{model, answers, usage}` out — from a hosted OpenAI-compatible model (LM Studio, Ollama, vLLM), so a
Jev contract client can run without the hosted API and without an API key. Every question's `criteria`
become SemIf options.

## Run

```bash
semif-jevsrv --port 8090   # uses ./.env (SEMIF_REMOTE_*); --env-file PATH for another file
```

```
SemIf Jev choices on http://127.0.0.1:8090/v1/systemone (model qwen3.5-4b, Ctrl+C to stop)
```

`POST /v1/systemone` (TypeSafe's path) and `POST /v1/choices` answer identically, so a client that
already speaks `/v1/systemone` needs only a base-URL change. `GET /` reports the service, its paths,
and the configured model. Configuration comes from `.env` (`SEMIF_REMOTE_BASE_URL`,
`SEMIF_REMOTE_MODEL`, `SEMIF_REMOTE_API_KEY`, `SEMIF_REMOTE_TIMEOUT`, `SEMIF_REMOTE_TOP_LOGPROBS`,
`SEMIF_REMOTE_REASONING_EFFORT`); `--host`, `--port` and `--env-file` are command-line overrides.

```json
{"model": "qwen3.5-4b",
 "state": {"page": {"url": "https://example.test/flights", "title": "Flights", "text": "Where from?..."},
           "elements": [{"index": "1", "label": "Where from?", "role": "combobox", "value": ""}],
           "recent_actions": []},
 "questions": {
   "operation": {"type": "choice",
     "criteria": {"TYPE_TEXT": "Enter or replace text in an editable field.",
                  "CLICK": "Click an element, button, menu option, or suggestion.",
                  "WAIT": "Wait when the needed control is absent or results load.",
                  "BLOCKED": "No supported operation can progress."},
     "instructions": {"goal": "Find a one-way flight from Zurich to London on 2026-09-20"}},
   "type_text_target": {"type": "choice",
     "criteria": {"1": {"element": "[1] Where from?", "role": "combobox", "current_value": ""}},
     "instructions": {"goal": "Find a one-way flight from Zurich to London on 2026-09-20"}}}}
```

```json
{"model": "qwen3.5-4b",
 "answers": {
   "operation": {"choice": "TYPE_TEXT", "confidence": 0.4806,
                 "probabilities": {"TYPE_TEXT": 0.4806, "CLICK": 0.4016, "WAIT": 0.0668, "BLOCKED": 0.051},
                 "prompt_sha256": "…", "prompt_version": "jev-choices-remote-v1", "model_calls": 1},
   "type_text_target": {"choice": "1", "confidence": 1.0, "probabilities": {"1": 1.0},
                        "prompt_version": "jev-choices-single-candidate-v1", "model_calls": 0}},
 "usage": {"questions": 2, "model_calls": 1, "elapsed_seconds": 0.516}}
```

## How questions are scored

| Criteria offered | Readout | Model calls |
|---|---|---|
| 1 | the only candidate, probability 1.0 — ranking a single option carries no information | 0 |
| 2-16 | one lettered-option logprob readout over all criteria (`A`–`P`), as in `semif-score --backend remote` | 1 |
| 17 or more | one yes/no relevance readout per criterion, normalized across criteria | one per criterion |

Criteria may be description strings or target dicts (`{element, role, current_value, ...}`), which are
rendered as `key: value` lines. The request's `model` is forwarded on every call; without it the
configured `SEMIF_REMOTE_MODEL` is used.

## Client compatibility

The answer satisfies a Jev contract client's validation: `choice` is the probability argmax,
`probabilities` covers exactly the offered criteria and sums to one, and `confidence` is in `[0, 1]`.
[jev-ultrafast](https://github.com/browser-use/jev-ultrafast) — a browser agent whose action space is
chosen, not generated — points at this server with:

```bash
TYPESAFE_API_BASE=http://127.0.0.1:8090
TYPESAFE_API_PATH=/v1/choices
TYPESAFE_API_KEY=
TYPESAFE_MODEL=qwen3.5-4b
```

## Limits

- `confidence` is the top probability: a ranking signal, not calibrated confidence. Probabilities are
  conditional on the offered criteria, as in every SemIf readout.
- The server inherits the hosted model's context window. Large element tables fail loudly with the
  upstream HTTP error rather than guessing or truncating.
- Remote numbers are not comparable to the pinned native BF16 headline results: the host server
  applies its own chat template and tokenizer.
- The server does not translate SemIf's `question` + `options[]` row format into the contract's
  `questions` map, and it does not verify outcomes. A `DONE`-style choice is not proof of success.
