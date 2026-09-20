import json
import sys

import pytest

from semif_phase1 import remote
from semif_phase1.cli import main

@pytest.fixture(autouse=True)
def _isolate_process_env(monkeypatch):
    for key in ("SEMIF_REMOTE_BASE_URL", "SEMIF_REMOTE_MODEL", "SEMIF_REMOTE_API_KEY",
                "SEMIF_REMOTE_REVISION", "SEMIF_REMOTE_TIMEOUT", "SEMIF_REMOTE_TOP_LOGPROBS",
                "SEMIF_REMOTE_REASONING_EFFORT"):
        monkeypatch.delenv(key, raising=False)

ROW = {
    "id": "route-1",
    "state": "Customer cannot access an account after a password reset.",
    "question": "Which queue should handle this request?",
    "options": [
        {"id": "access", "description": "Account access support."},
        {"id": "billing", "description": "Billing support."},
    ],
}

def _response(logprobs):
    return {
        "choices": [
            {"message": {"content": "A"}, "logprobs": {"content": [{"token": "A", "logprob": logprobs[0],
                                                                     "top_logprobs": [
                                                                         {"token": letter, "logprob": value}
                                                                         for letter, value in zip("AB", logprobs)]}]}},
        ],
        "usage": {"prompt_tokens": 42, "completion_tokens": 1},
    }

class FakeClient(remote.RemoteClient):
    def __init__(self, payloads):
        super().__init__(base_url="http://localhost:1234/v1", model="test-model")
        self.payloads = list(payloads)
        self.seen = []

    def chat(self, messages):
        self.seen.append(messages)
        return self.payloads.pop(0)

def test_load_model_validates_without_network():
    with pytest.raises(ValueError, match="http"):
        remote.load_model("model", "label", base_url="not-a-url")
    with pytest.raises(ValueError, match="top_logprobs"):
        remote.load_model("model", "label", top_logprobs=21)
    with pytest.raises(ValueError, match="positive"):
        remote.load_model("model", "label", timeout_seconds=0)
    client, tokenizer, metadata = remote.load_model("model", "label")
    assert tokenizer is None
    assert metadata["backend"] == "remote"

def test_extract_handles_leading_space_and_bytes():
    response = {"choices": [{"logprobs": {"content": [{
        "token": " A", "logprob": -0.2,
        "top_logprobs": [{"token": "B", "logprob": -1.7},
                         {"bytes": [66], "logprob": -1.7}],
    }]}}]}
    assert response["choices"][0]["logprobs"]["content"][0]["top_logprobs"][1]["bytes"] == [66]
    assert remote.extract_option_logprobs(response, 2) == pytest.approx([-0.2, -1.7])

def test_extract_rejects_missing_letter():
    response = {"choices": [{"logprobs": {"content": [{
        "token": "A", "logprob": -0.1, "top_logprobs": []}]}}]}
    with pytest.raises(ValueError, match="lacks option letters"):
        remote.extract_option_logprobs(response, 2)

def test_extract_rejects_missing_logprobs_block():
    with pytest.raises(ValueError, match="logprobs"):
        remote.extract_option_logprobs({"choices": [{"message": {"content": "A"}}]}, 2)

def test_score_returns_conditional_distribution():
    client = FakeClient([_response([-0.3, -1.9])])
    result = remote.score(client, None, ROW, {"backend": "remote"})
    assert result["id"] == "route-1"
    assert result["option_ids"] == ["access", "billing"]
    assert result["probabilities"] == pytest.approx([0.832, 0.168], abs=1e-3)
    assert result["prompt_version"] == remote.PROMPT_VERSION
    assert result["input_tokens"] == 42
    assert "uncalibrated" in result["probability_status"]
    assert client.seen[0][0]["role"] == "system"

def test_serial_tracks_state_hits():
    client = FakeClient([_response([-0.1, -2.0]), _response([-0.4, -0.5])])
    scorer = remote.SerialPrefixScorer(client, None, {"backend": "remote"})
    first = scorer.score(ROW)
    second = scorer.score(dict(ROW, id="route-2"))
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True

def test_shared_requires_exact_state_and_unique_ids():
    client = FakeClient([_response([-0.1, -2.0])])
    with pytest.raises(ValueError, match="exact state"):
        remote.score_shared(client, None, [ROW, dict(ROW, id="x", state="other")], {})
    with pytest.raises(ValueError, match="unique"):
        remote.score_shared(client, None, [ROW, ROW], {})
    results, timing = remote.score_shared(client, None, [ROW], {"backend": "remote"})
    assert len(results) == 1 and timing["batch_size"] == 1

def test_load_dotenv_parses_and_never_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMIF_REMOTE_MODEL", "from-process-env")
    monkeypatch.delenv("SEMIF_REMOTE_BASE_URL", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# comment\n"
        "export SEMIF_REMOTE_MODEL=from-file\n"
        "SEMIF_REMOTE_BASE_URL='http://host:1234/v1'\n"
        'SEMIF_REMOTE_API_KEY="secret"\n'
        "NOT_A_VALID_LINE\n"
        "123BAD=ignored\n"
    )
    loaded = remote.load_dotenv(dotenv)
    assert loaded == {"SEMIF_REMOTE_BASE_URL": "http://host:1234/v1",
                      "SEMIF_REMOTE_API_KEY": "secret"}
    assert remote.load_dotenv(tmp_path / "missing.env") == {}

def test_chat_disables_reasoning_by_default():
    import json as _json
    import urllib.request as _url

    client = remote.RemoteClient(base_url="http://x/v1", model="m")
    captured = {}
    real_request, real_urlopen = _url.Request, _url.urlopen

    class FakeRequest:
        def __init__(self, url, data=None, headers=None, method=None):
            captured["payload"] = _json.loads(data.decode())

        def add_header(self, *args):
            pass

    def boom(*args, **kwargs):
        raise AssertionError("stop after capture")

    _url.Request, _url.urlopen = FakeRequest, boom
    try:
        with pytest.raises(RuntimeError, match="stop after capture"):
            client.chat([{"role": "user", "content": "hi"}])
    finally:
        _url.Request, _url.urlopen = real_request, real_urlopen
    assert captured["payload"]["reasoning_effort"] == "none"
    assert captured["payload"]["top_logprobs"] == 20

def test_cli_rejects_remote_reranker_and_mismatched_options(tmp_path, monkeypatch, capsys):
    source = tmp_path / "input.jsonl"
    source.write_text(json.dumps(ROW) + "\n")
    output = tmp_path / "out.jsonl"
    monkeypatch.setattr(sys, "argv", ["semif-score", "--backend", "remote", "--mode", "reranker",
                                      "--model", "m", "--revision", "r",
                                      "--input", str(source), "--output", str(output)])
    with pytest.raises(SystemExit):
        main()
    assert "reranker requires torch" in capsys.readouterr().err

    monkeypatch.setattr(sys, "argv", ["semif-score", "--mode", "direct", "--remote-timeout", "5",
                                      "--model", "m", "--revision", "r",
                                      "--input", str(source), "--output", str(output)])
    with pytest.raises(SystemExit):
        main()
    assert "require --backend remote" in capsys.readouterr().err

def test_cli_remote_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(remote.RemoteClient, "chat", lambda self, messages: _response([-0.2, -1.2]))
    source = tmp_path / "input.jsonl"
    source.write_text(json.dumps(ROW) + "\n")
    output = tmp_path / "out.jsonl"
    monkeypatch.setattr(sys, "argv", ["semif-score", "--backend", "remote", "--mode", "direct",
                                      "--model", "hosted-model", "--revision", "lm-studio",
                                      "--remote-base-url", "http://localhost:1234/v1",
                                      "--input", str(source), "--output", str(output)])
    monkeypatch.delenv("SEMIF_REMOTE_BASE_URL", raising=False)
    main()
    row = json.loads(output.read_text())
    assert row["model"]["backend"] == "remote"
    assert sum(row["probabilities"]) == pytest.approx(1.0)

def test_cli_remote_reads_model_from_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(remote.RemoteClient, "chat", lambda self, messages: _response([-0.2, -1.2]))
    for key in ("SEMIF_REMOTE_MODEL", "SEMIF_REMOTE_REVISION", "SEMIF_REMOTE_BASE_URL",
                "SEMIF_REMOTE_API_KEY", "SEMIF_REMOTE_TIMEOUT", "SEMIF_REMOTE_TOP_LOGPROBS"):
        monkeypatch.delenv(key, raising=False)
    dotenv = tmp_path / "test.env"
    dotenv.write_text(
        "SEMIF_REMOTE_BASE_URL=http://host:1234/v1\n"
        "SEMIF_REMOTE_MODEL=env-file-model\n"
        "SEMIF_REMOTE_REVISION=env-file-label\n"
    )
    source = tmp_path / "input.jsonl"
    source.write_text(json.dumps(ROW) + "\n")
    output = tmp_path / "out.jsonl"
    monkeypatch.setattr(sys, "argv", ["semif-score", "--backend", "remote", "--mode", "direct",
                                      "--env-file", str(dotenv),
                                      "--input", str(source), "--output", str(output)])
    main()
    row = json.loads(output.read_text())
    assert row["model"]["source"] == "env-file-model"
    assert row["model"]["revision"] == "env-file-label"
    assert row["model"]["base_url"] == "http://host:1234/v1"

def test_cli_remote_missing_model_fails_loudly(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for key in ("SEMIF_REMOTE_MODEL", "SEMIF_REMOTE_REVISION"):
        monkeypatch.delenv(key, raising=False)
    source = tmp_path / "input.jsonl"
    source.write_text(json.dumps(ROW) + "\n")
    output = tmp_path / "out.jsonl"
    monkeypatch.setattr(sys, "argv", ["semif-score", "--backend", "remote", "--mode", "direct",
                                      "--input", str(source), "--output", str(output)])
    with pytest.raises(SystemExit):
        main()
    assert "needs a model" in capsys.readouterr().err
