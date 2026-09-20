# TypeSafe (Jev) proxy

`semif-proxy` is a small stdlib-only reverse proxy for TypeSafe's System One
endpoint. TypeSafe expects one secret API key and its `POST /v1/systemone`
contract is not OpenAI-compatible, so this sits in front of it and lets any
client talk to it with a **local** key you generate.

- The real key never leaves `.env`; the proxy injects it server-side.
- Clients authenticate with `SEMIF_PROXY_API_KEY`, generated for you.
- Every path is forwarded, including `/typesafe/...` (mirroring LiteLLM's
  pass-through), so a client configured for LiteLLM's `/typesafe/` route
  works unchanged.
- `429`/`529` responses and transient network errors are retried with
  exponential backoff, as the [TypeSafe API docs](https://docs.typesafe.ai/api)
  advise.

## 1. Paste the TypeSafe key

Open `backend/.env` (copy `.env.example` if it does not exist) and set the
real key TypeSafe gave you:

```bash
TYPESAFE_API_KEY=ts_live_paste_your_key_here
```

`.env` is gitignored. Do not pass the key on the command line — it would end
up in your shell history.

Optional overrides:

| Env key | Meaning | Default |
|---|---|---|
| `TYPESAFE_API_KEY` | Real TypeSafe key the proxy injects | (required) |
| `TYPESAFE_API_BASE` | Upstream base URL | `https://api.typesafe.ai` |
| `SEMIF_PROXY_API_KEY` | Local key clients send (auto-generated) | generated |
| `SEMIF_PROXY_HOST` | Bind host | `127.0.0.1` |
| `SEMIF_PROXY_PORT` | Bind port | `4001` |
| `SEMIF_PROXY_TIMEOUT` | Seconds per upstream request | `120` |

## 2. Generate the local key

```bash
pip install -e '.[test]'   # registers the semif-proxy command
semif-proxy --generate-key
```

This writes `SEMIF_PROXY_API_KEY=sk-semif-...` into `.env` and prints it.
Generating again rotates (invalidates) the previous key. If you start the
proxy without a key, it generates one for you automatically.

## 3. Run it

```bash
semif-proxy
```

```
SemIf TypeSafe proxy on http://127.0.0.1:4001
  upstream      https://api.typesafe.ai
  upstream key  ts_live_pas...here
  client key    sk-semif-3a4...009b
  evaluate      POST http://127.0.0.1:4001/typesafe/v1/systemone
```

Then point your client at the proxy instead of `https://api.typesafe.ai`:

```bash
curl -X POST http://127.0.0.1:4001/typesafe/v1/systemone \
  -H "Authorization: Bearer $SEMIF_PROXY_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "state": "Help! My payouts have been failing for 3 days.",
    "model": "jev-latest",
    "questions": {
      "department": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {"billing": "Payments, invoicing, refunds",
                     "technical": "Bugs, outages, integrations",
                     "sales": "Pricing, upgrades, new accounts"}
      }
    }
  }'
```

`GET /` and `GET /health` return proxy status without forwarding and without
auth; they mask both keys.

## Notes and limitations

- Binds to `127.0.0.1` by default. It is a local development proxy, not a
  hardened internet-facing gateway; use `--host 0.0.0.0` only deliberately.
- Both the local proxy key and the real TypeSafe key are accepted from
  clients, so pasting the TypeSafe key straight into a client still works.
  `--no-auth` disables client auth entirely (debugging only).
- The proxy does not translate SemIf's row format (`question` + `options[]`)
  into TypeSafe's `questions` map; it forwards the TypeSafe shape as-is.
- Costs are billed to the TypeSafe account behind `TYPESAFE_API_KEY`; the
  proxy adds no caching, so every forwarded request is a real evaluation.
- No SDK dependency: HTTP is `urllib`, matching the `remote` backend.
