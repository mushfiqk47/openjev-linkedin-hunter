import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from semif_phase1 import typesafe_proxy
from semif_phase1.typesafe_proxy import Upstream, main, make_handler, normalize_path


class _UpstreamHandler(BaseHTTPRequestHandler):
    queue: list = []
    seen: list = []

    def _reply(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        _UpstreamHandler.seen.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
        )
        status, payload = _UpstreamHandler.queue.pop(0)
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _reply
    do_POST = _reply

    def log_message(self, *args):
        pass


@pytest.fixture(autouse=True)
def _isolate_process_env(monkeypatch):
    for key in ("TYPESAFE_API_KEY", "TYPESAFE_API_BASE", "SEMIF_PROXY_API_KEY",
                "SEMIF_PROXY_HOST", "SEMIF_PROXY_PORT", "SEMIF_PROXY_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def upstream_server():
    _UpstreamHandler.queue = []
    _UpstreamHandler.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _start(handler) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _call(url, key=None, body=None, method="POST"):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if key:
        request.add_header("Authorization", f"Bearer {key}")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


SUBJECT = {"state": "Help! My payouts have been failing.", "model": "jev-latest",
           "questions": {"is_urgent": {"type": "noul", "instructions": "Urgent?"}}}


def test_generate_api_key_shape_and_uniqueness():
    keys = {typesafe_proxy.generate_api_key() for _ in range(50)}
    assert len(keys) == 50
    assert all(key.startswith("sk-semif-") and len(key) == len("sk-semif-") + 48 for key in keys)


def test_normalize_path_strips_typesafe_prefix():
    assert normalize_path("/typesafe/v1/systemone") == "/v1/systemone"
    assert normalize_path("/typesafe/v1/models?limit=5") == "/v1/models?limit=5"
    assert normalize_path("/typesafe") == "/"
    assert normalize_path("/v1/systemone") == "/v1/systemone"
    assert normalize_path("") == "/"


def test_upsert_env_replaces_and_preserves(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "TYPESAFE_API_KEY=real-secret\n"
        "export SEMIF_PROXY_API_KEY=sk-semif-old\n"
        "SEMIF_REMOTE_MODEL=qwen3.5-4b\n"
    )
    new_key = typesafe_proxy.generate_api_key()
    typesafe_proxy.upsert_env(env, {"SEMIF_PROXY_API_KEY": new_key})
    text = env.read_text()
    assert "TYPESAFE_API_KEY=real-secret" in text
    assert "SEMIF_REMOTE_MODEL=qwen3.5-4b" in text
    assert "# comment" in text
    assert f"SEMIF_PROXY_API_KEY={new_key}" in text
    assert "sk-semif-old" not in text

    created = tmp_path / "sub" / ".env"
    typesafe_proxy.upsert_env(created, {"SEMIF_PROXY_API_KEY": "sk-semif-new"})
    assert created.read_text().strip() == "SEMIF_PROXY_API_KEY=sk-semif-new"


def test_upstream_injects_real_key_and_passes_body(upstream_server):
    _UpstreamHandler.queue.append((200, {"model": "jev-1.13.0", "answers": {}}))
    upstream = Upstream(base_url=upstream_server, api_key="real-secret")
    body = json.dumps(SUBJECT).encode()
    status, content_type, payload = upstream.request("POST", "/v1/systemone", body, "application/json")
    assert status == 200 and content_type == "application/json"
    assert json.loads(payload)["model"] == "jev-1.13.0"
    sent = _UpstreamHandler.seen[0]
    assert sent["authorization"] == "Bearer real-secret"
    assert sent["path"] == "/v1/systemone"
    assert json.loads(sent["body"]) == SUBJECT


def test_upstream_retries_on_429_then_succeeds(upstream_server):
    _UpstreamHandler.queue.extend([(429, {"error": "rate limited"}), (200, {"model": "jev-latest"})])
    upstream = Upstream(base_url=upstream_server, api_key="k", retries=2, backoff_seconds=0.0,
                        sleep=lambda *_: None)
    status, _, payload = upstream.request("POST", "/v1/systemone", b"{}", "application/json")
    assert status == 200 and json.loads(payload)["model"] == "jev-latest"
    assert len(_UpstreamHandler.seen) == 2


def test_upstream_passes_through_terminal_error(upstream_server):
    _UpstreamHandler.queue.append((422, {"error": "invalid question type"}))
    upstream = Upstream(base_url=upstream_server, api_key="k", retries=3, backoff_seconds=0.0,
                        sleep=lambda *_: None)
    status, _, payload = upstream.request("POST", "/v1/systemone", b"{}", "application/json")
    assert status == 422 and json.loads(payload)["error"] == "invalid question type"
    assert len(_UpstreamHandler.seen) == 1


def test_upstream_rejects_bad_configuration():
    with pytest.raises(ValueError, match="http"):
        Upstream(base_url="nope", api_key="k")
    with pytest.raises(ValueError, match="API key"):
        Upstream(base_url="http://localhost:1", api_key="")


def test_proxy_requires_key_and_forwards_with_real_key(upstream_server):
    reply = {"model": "jev-latest", "answers": {"is_urgent": {"noul": 0.92}}}
    _UpstreamHandler.queue.extend([(200, reply), (200, reply)])
    upstream = Upstream(base_url=upstream_server, api_key="real-secret")
    server = _start(make_handler(upstream, "sk-semif-client"))
    port = server.server_address[1]
    try:
        url = f"http://127.0.0.1:{port}/typesafe/v1/systemone"
        assert _call(url, body=SUBJECT)[0] == 401
        assert _call(url, key="wrong-key", body=SUBJECT)[0] == 401
        status, payload = _call(url, key="sk-semif-client", body=SUBJECT)
        assert status == 200 and payload["answers"]["is_urgent"]["noul"] == 0.92
        assert _UpstreamHandler.seen[-1]["authorization"] == "Bearer real-secret"
        assert _UpstreamHandler.seen[-1]["path"] == "/v1/systemone"
        # the real key is also accepted directly, so pasting it into a client works
        assert _call(url, key="real-secret", body=SUBJECT)[0] == 200
    finally:
        server.shutdown()
        server.server_close()


def test_proxy_health_is_open_and_masks_keys(upstream_server):
    upstream = Upstream(base_url=upstream_server, api_key="real-secret-value")
    server = _start(make_handler(upstream, "sk-semif-client-abcdef"))
    port = server.server_address[1]
    try:
        status, payload = _call(f"http://127.0.0.1:{port}/health", method="GET")
        assert status == 200 and payload["status"] == "ok"
        assert payload["models"] == ["jev-latest"]
        assert "real-secret-value" not in json.dumps(payload)
        assert "sk-semif-client-abcdef" not in json.dumps(payload)
    finally:
        server.shutdown()
        server.server_close()


def test_proxy_can_run_without_auth(upstream_server):
    _UpstreamHandler.queue.append((200, {"model": "jev-latest"}))
    upstream = Upstream(base_url=upstream_server, api_key="real-secret")
    server = _start(make_handler(upstream, "", auth_required=False))
    port = server.server_address[1]
    try:
        status, _ = _call(f"http://127.0.0.1:{port}/v1/systemone", body=SUBJECT)
        assert status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_generate_key_writes_env_and_exits(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    env.write_text("TYPESAFE_API_KEY=real-secret\n")
    monkeypatch.setattr(sys, "argv", ["semif-proxy", "--generate-key", "--env-file", str(env)])
    main()
    key = [line for line in env.read_text().splitlines() if line.startswith("SEMIF_PROXY_API_KEY=")][0]
    assert "TYPESAFE_API_KEY=real-secret" in env.read_text()
    assert key.removeprefix("SEMIF_PROXY_API_KEY=") in capsys.readouterr().out


def test_missing_typesafe_key_fails_loudly(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["semif-proxy"])
    with pytest.raises(SystemExit):
        main()
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err
