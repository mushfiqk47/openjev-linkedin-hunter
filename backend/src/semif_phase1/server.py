"""Local decision UI backed by a hosted model (LM Studio, ...).

Serves a single dependency-free page where you paste a state, question and
options, then scores them through the ``remote`` backend configured from
the ``.env`` file. Stdlib only; no build step, no CDN, no telemetry.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import remote as remote_backend
from .core import LETTERS, validate_row

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>SemIf — local decisions</title>
<style>
:root { color-scheme: light dark; }
body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
textarea, input[type=text] { width: 100%; box-sizing: border-box; padding: .5rem; font: inherit; }
textarea { min-height: 6rem; }
.option { display: flex; gap: .5rem; margin: .35rem 0; }
.option input { flex: 1; }
button { font: inherit; padding: .5rem 1rem; cursor: pointer; }
.row { display: flex; gap: .5rem; align-items: center; margin: .5rem 0; }
.bar { height: 1.1rem; background: #4a90d9; display: inline-block; min-width: 2px; }
.choice { display: grid; grid-template-columns: 2rem 1fr 4rem; gap: .5rem; align-items: center; margin: .3rem 0; }
.choice.winner { font-weight: bold; }
.error { color: #b3261e; }
.muted { opacity: .7; font-size: .9rem; }
pre { white-space: pre-wrap; background: rgba(127,127,127,.12); padding: .5rem; }
</style>
</head>
<body>
<h1>SemIf — local decisions</h1>
<p class="muted">Scores <span id="model">…</span> through your hosted model. Probabilities are conditional on the listed options, not calibrated confidence.</p>
<label>State<textarea id="state">A customer says a password reset succeeded, but every login attempt still returns “account locked”. Two unlock emails were requested and neither arrived.</textarea></label>
<p><label>Question<input id="question" type="text" value="Which queue should handle this request?" /></label></p>
<fieldset><legend>Options (2–16)</legend>
<div id="options"></div>
<div class="row"><button id="add" type="button">+ add</button><button id="remove" type="button">− remove</button><span id="count" class="muted"></span></div>
</fieldset>
<p><button id="run" type="button">Score decision</button> <span id="status" class="muted"></span></p>
<div id="out"></div>
<script>
const MAX = 16, MIN = 2;
const box = document.getElementById("options");
function rows() { return [...box.querySelectorAll(".option")]; }
function sync() {
  rows().forEach((r, i) => r.querySelector("b").textContent = String.fromCharCode(65 + i));
  document.getElementById("count").textContent = rows().length + " / " + MAX;
}
function add(value = "") {
  if (rows().length >= MAX) return;
  const d = document.createElement("div");
  d.className = "option";
  d.innerHTML = "<b></b><input type='text' placeholder='Option description' />";
  d.querySelector("input").value = value;
  box.append(d); sync();
}
document.getElementById("add").onclick = () => add();
document.getElementById("remove").onclick = () => { const r = rows(); if (r.length > MIN) r.at(-1).remove(); sync(); };
["Account access support", "Billing support", "Close as resolved"].forEach(add);
fetch("/api/model").then(r => r.json()).then(m => {
  document.getElementById("model").textContent = m.source + " (" + m.revision + ")";
});
document.getElementById("run").onclick = async () => {
  const out = document.getElementById("out"), status = document.getElementById("status");
  out.innerHTML = ""; status.textContent = "scoring…";
  const options = rows().map(r => r.querySelector("input").value.trim());
  try {
    const res = await fetch("/api/score", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({state: document.getElementById("state").value,
        question: document.getElementById("question").value, options})});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
    status.textContent = "done in " + data.total_seconds.toFixed(2) + " s";
    const best = data.probabilities.indexOf(Math.max(...data.probabilities));
    out.innerHTML = data.option_ids.map((id, i) =>
      `<div class="choice${i === best ? " winner" : ""}"><b>${String.fromCharCode(65 + i)}</b>` +
      `<span><span class="bar" style="width:${(data.probabilities[i] * 100).toFixed(1)}%"></span> ${id}</span>` +
      `<span>${data.probabilities[i].toFixed(3)}</span></div>`).join("") +
      `<p class="muted">${data.probability_status}</p><details><summary>raw</summary><pre>${JSON.stringify(data, null, 1).replace(/</g, "&lt;")}</pre></details>`;
  } catch (e) { status.textContent = ""; out.innerHTML = `<p class="error">${String(e.message || e).replace(/</g, "&lt;")}</p>`; }
};
</script>
</body>
</html>
"""


def normalize_options(options) -> list[dict]:
    """Accept description strings or {id, description} objects."""
    normalized = []
    for index, option in enumerate(options):
        if isinstance(option, str):
            normalized.append({"id": f"opt-{LETTERS[index].lower()}", "description": option})
        elif isinstance(option, dict):
            normalized.append({"id": option.get("id") or f"opt-{LETTERS[index].lower()}",
                               "description": option.get("description", "")})
        else:
            raise ValueError("Each option must be a string or an {id, description} object")
    return normalized


def score_decision(client, metadata: dict, payload: dict) -> dict:
    """Validate a UI payload and score it through the remote backend."""
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    state = payload.get("state", "")
    if isinstance(state, str):
        state = state.strip()
    row = {
        "id": str(payload.get("id") or "ui-decision"),
        "state": state if isinstance(state, (dict, list)) else state,
        "question": str(payload.get("question", "")).strip(),
        "options": normalize_options(payload.get("options") or []),
    }
    validate_row(row)
    return remote_backend.score(client, None, row, metadata)


def make_handler(client, metadata):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SemIfUI/1.0"

        def _send(self, code: int, body: bytes, content_type: str):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/model":
                public = {key: metadata[key] for key in ("source", "revision", "backend") if key in metadata}
                self._send(200, json.dumps(public).encode(), "application/json")
            else:
                self._send(404, b'{"error": "not found"}', "application/json")

        def do_POST(self):
            if self.path != "/api/score":
                self._send(404, b'{"error": "not found"}', "application/json")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"null")
                result = score_decision(client, metadata, payload)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local SemIf decision UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--env-file", type=Path, default=None,
                        help="Dotenv file with SEMIF_REMOTE_* settings (default: ./.env if present).")
    args = parser.parse_args()
    env_file = args.env_file or Path(".env")
    if args.env_file and not env_file.exists():
        parser.error(f"Env file not found: {env_file}")
    if env_file.exists():
        remote_backend.load_dotenv(env_file)
    import os

    model_name = os.environ.get(remote_backend.ENV_MODEL)
    revision = os.environ.get(remote_backend.ENV_REVISION)
    if not model_name or not revision:
        parser.error("Set SEMIF_REMOTE_MODEL and SEMIF_REMOTE_REVISION in the env file")
    client, _, metadata = remote_backend.load_model(
        model_name, revision,
        base_url=os.environ.get(remote_backend.ENV_BASE_URL) or remote_backend.DEFAULT_BASE_URL,
        api_key=os.environ.get(remote_backend.ENV_API_KEY) or "lm-studio",
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(client, metadata))
    print(f"SemIf UI on http://{args.host}:{args.port}  (model {model_name}, Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
