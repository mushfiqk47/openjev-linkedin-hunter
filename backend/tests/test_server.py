import json
import threading
import urllib.request
from http.client import HTTPConnection

import pytest

from semif_phase1 import remote, server

class FakeClient(remote.RemoteClient):
    def __init__(self):
        super().__init__(base_url="http://localhost:1234/v1", model="test-model")

    def chat(self, messages):
        return {"choices": [{"logprobs": {"content": [{
            "token": "A", "logprob": -0.2,
            "top_logprobs": [{"token": "A", "logprob": -0.2},
                             {"token": "B", "logprob": -1.7}],
        }]}}], "usage": {"prompt_tokens": 10, "completion_tokens": 1}}

@pytest.fixture()
def app():
    metadata = {"source": "m", "revision": "r", "backend": "remote"}
    handler = server.make_handler(FakeClient(), metadata)
    from http.server import ThreadingHTTPServer

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()

def post(url, payload):
    request = urllib.request.Request(
        url + "/api/score", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())

def test_page_has_no_external_dependencies():
    assert 'id="state"' in server.PAGE and 'id="run"' in server.PAGE
    for marker in ("https://", 'src="http', 'href="http'):
        assert marker not in server.PAGE

def test_score_endpoint_returns_distribution(app):
    status, data = post(app, {"state": "Evidence", "question": "Which?",
                              "options": ["First thing", "Second thing"]})
    assert status == 200
    assert data["option_ids"] == ["opt-a", "opt-b"]
    assert sum(data["probabilities"]) == pytest.approx(1.0)
    assert "uncalibrated" in data["probability_status"]

def test_score_endpoint_rejects_bad_input(app):
    status, data = post(app, {"state": "", "question": "Which?", "options": ["only-one"]})
    assert status == 400
    assert "error" in data

def test_normalize_options_accepts_objects_and_strings():
    options = server.normalize_options(["Plain", {"id": "x", "description": "Why"}])
    assert options[0]["description"] == "Plain" and options[1]["id"] == "x"
    with pytest.raises(ValueError):
        server.normalize_options(["ok", "fine", 42])
