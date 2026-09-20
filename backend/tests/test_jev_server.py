"""Offline contracts for the Jev choice-contract server."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from semif_phase1 import jev_server
from semif_phase1.remote import RemoteClient

LETTERS = "ABCDEFGHIJKLMNOP"
METADATA = {"source": "fallback-model", "revision": "test", "backend": "remote"}


class FakeClient(RemoteClient):
    """Registered in place of a hosted server; records every request."""

    def __init__(self, payloads=()):
        super().__init__(base_url="http://localhost:1234/v1", model="configured-model")
        self.payloads = list(payloads)
        self.seen = []

    def chat(self, messages, model=None):
        self.seen.append({"messages": messages, "model": model})
        if not self.payloads:
            raise AssertionError("unexpected model call")
        return self.payloads.pop(0)


def letters_response(values):
    return {"choices": [{"logprobs": {"content": [{
        "token": LETTERS[0], "logprob": values[0],
        "top_logprobs": [{"token": letter, "logprob": value} for letter, value in zip(LETTERS, values)],
    }]}}], "usage": {"prompt_tokens": 12, "completion_tokens": 1}}


def yes_no_response(yes, no):
    return {"choices": [{"logprobs": {"content": [{
        "token": "yes", "logprob": yes,
        "top_logprobs": [{"token": "yes", "logprob": yes}, {"token": "no", "logprob": no}],
    }]}}]}


def request_body(questions, state=None):
    return {"model": "qwen3.5-4b", "state": state or {"page": {"title": "Flights", "text": "Search flights."}},
            "questions": questions}


def choice_question(criteria):
    return {"type": "choice", "criteria": criteria,
            "instructions": {"goal": "Find a one-way flight from Zurich to London"}}


def test_request_needs_choice_questions_with_criteria():
    with pytest.raises(ValueError, match="JSON object"):
        jev_server.parse_request(None)
    with pytest.raises(ValueError, match="nonempty questions"):
        jev_server.parse_request({"questions": {}})
    with pytest.raises(ValueError, match="must be a choice question"):
        jev_server.parse_request({"questions": {"q": {"type": "free_text", "criteria": {"a": "b"}}}})
    with pytest.raises(ValueError, match="at least one criterion"):
        jev_server.parse_request({"questions": {"q": {"type": "choice", "criteria": {}}}})
    model, state, questions = jev_server.parse_request(request_body({"q": choice_question({"only": "one"})}))
    assert model == "qwen3.5-4b" and state["page"]["title"] == "Flights" and set(questions) == {"q"}


def test_row_keeps_criterion_keys_and_renders_target_dicts():
    question = choice_question({"1": {"element": "[1] Where from?", "role": "combobox", "current_value": ""},
                                "2": {"element": "[2] Where to?"}})
    row, keys = jev_server.build_row("type_text_target", {"page": "text"}, question)
    assert keys == ["1", "2"]
    assert [option["id"] for option in row["options"]] == ["1", "2"]
    assert row["options"][0]["description"] == "element: [1] Where from?\nrole: combobox\ncurrent_value: "
    assert row["question"] == "Find a one-way flight from Zurich to London"


def test_single_candidate_head_answers_without_a_model_call():
    client = FakeClient([letters_response([-0.1, -2.0, -3.0, -4.0])])
    body = request_body({
        "operation": choice_question({"TYPE_TEXT": "Enter text.", "CLICK": "Click something.",
                                      "WAIT": "Wait.", "BLOCKED": "Stop."}),
        "type_text_target": choice_question({"1": {"element": "[1] Where from?"}}),
    })
    result = jev_server.serve_request(client, METADATA, body)
    assert len(client.seen) == 1  # the single-candidate head costs nothing
    assert result["usage"]["questions"] == 2 and result["usage"]["model_calls"] == 1
    assert result["usage"]["elapsed_seconds"] >= 0
    assert result["answers"]["type_text_target"] == {
        "choice": "1", "probabilities": {"1": 1.0}, "confidence": 1.0,
        "prompt_version": jev_server.SINGLE_PROMPT_VERSION, "model_calls": 0}


def test_direct_readout_is_argmax_normalized_and_forwards_the_request_model():
    client = FakeClient([letters_response([-0.2, -1.5, -4.0])])
    body = request_body({"operation": choice_question({"CLICK": "Click.", "WAIT": "Wait.", "DONE": "Done."})})
    result = jev_server.serve_request(client, METADATA, body)
    answer = result["answers"]["operation"]
    assert answer["choice"] == "CLICK" == max(answer["probabilities"], key=answer["probabilities"].get)
    assert sum(answer["probabilities"].values()) == pytest.approx(1.0)
    assert answer["confidence"] == pytest.approx(answer["probabilities"]["CLICK"])
    assert answer["prompt_version"] == jev_server.PROMPT_VERSION
    assert result["model"] == "qwen3.5-4b" and client.seen[0]["model"] == "qwen3.5-4b"
    assert len(client.seen[0]["messages"]) == 2


def test_absent_request_model_falls_back_to_the_configured_source():
    client = FakeClient([letters_response([-0.3, -0.9])])
    result = jev_server.serve_request(client, METADATA, {"questions": {"q": choice_question({"a": "A", "b": "B"})}})
    assert result["model"] == "fallback-model" and client.seen[0]["model"] is None


def test_many_criteria_use_one_binary_readout_each():
    criteria = {str(index): {"element": f"[{index}] control"} for index in range(1, 18)}
    client = FakeClient([yes_no_response(-0.5, -2.0)] * 17)
    result = jev_server.serve_request(client, METADATA, request_body({"click_target": choice_question(criteria)}))
    answer = result["answers"]["click_target"]
    assert len(client.seen) == 17
    assert result["usage"]["model_calls"] == 17 and result["usage"]["questions"] == 1
    assert len(answer["probabilities"]) == 17 and sum(answer["probabilities"].values()) == pytest.approx(1.0)
    assert answer["prompt_version"] == jev_server.BINARY_PROMPT_VERSION
    assert answer["choice"] in answer["probabilities"]


def test_binary_readout_without_yes_no_logprobs_fails_loudly():
    client = FakeClient([letters_response([-0.5, -2.0])])
    criteria = {str(index): "candidate" for index in range(1, 18)}
    with pytest.raises(ValueError, match="yes/no"):
        jev_server.serve_request(client, METADATA, request_body({"q": choice_question(criteria)}))


def test_load_configuration_reads_the_environment(monkeypatch):
    monkeypatch.delenv("SEMIF_REMOTE_MODEL", raising=False)
    with pytest.raises(ValueError, match="SEMIF_REMOTE_MODEL"):
        jev_server.load_configuration()
    monkeypatch.setenv("SEMIF_REMOTE_MODEL", "qwen3.5-4b")
    client, metadata = jev_server.load_configuration()
    assert client.model == metadata["source"] == "qwen3.5-4b"
    monkeypatch.setenv("SEMIF_REMOTE_TIMEOUT", "not-a-number")
    with pytest.raises(ValueError, match="SEMIF_REMOTE_TIMEOUT"):
        jev_server.load_configuration()


def _serve(client):
    server = ThreadingHTTPServer(("127.0.0.1", 0), jev_server.make_handler(client, METADATA))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _post(url, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def test_handler_serves_both_contract_paths_and_404s_elsewhere():
    server = _serve(FakeClient([letters_response([-0.1, -1.0])] * 2))
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        body = request_body({"q": choice_question({"a": "A", "b": "B"})})
        for path in ("/v1/systemone", "/v1/choices"):
            status, payload = _post(base + path, body)
            assert status == 200 and payload["answers"]["q"]["choice"] == "a"
        assert _post(base + "/v1/other", body)[0] == 404
        with urllib.request.urlopen(base + "/", timeout=5) as response:
            assert json.load(response)["service"] == "semif-jev-choices"
    finally:
        server.shutdown()
        server.server_close()


def test_handler_separates_bad_requests_from_upstream_failures():
    class Broken(FakeClient):
        def chat(self, messages, model=None):
            raise RuntimeError("host server refused the request")

    healthy = _serve(FakeClient())
    try:
        url = f"http://127.0.0.1:{healthy.server_address[1]}/v1/systemone"
        assert _post(url, {"questions": {}})[0] == 400
        assert _post(url, {"questions": {"q": choice_question({"a": "A"})}})[0] == 200
    finally:
        healthy.shutdown()
        healthy.server_close()
    broken = _serve(Broken())
    try:
        url = f"http://127.0.0.1:{broken.server_address[1]}/v1/systemone"
        status, payload = _post(url, request_body({"q": choice_question({"a": "A", "b": "B"})}))
        assert status == 502 and "refused" in payload["error"]
    finally:
        broken.shutdown()
        broken.server_close()
