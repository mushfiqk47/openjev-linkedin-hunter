import json
import sys

import pytest

from semif_phase1.cli import main


ROW = {
    "id": "test",
    "state": "Evidence",
    "question": "Supported?",
    "options": [{"id": "yes", "description": "Yes"}, {"id": "no", "description": "No"}],
}


def test_existing_output_is_refused_before_loading(tmp_path, monkeypatch, capsys):
    source, output = tmp_path / "input.jsonl", tmp_path / "output.jsonl"
    source.write_text(json.dumps(ROW) + "\n")
    output.write_text("already here")
    monkeypatch.setattr(sys, "argv", ["semif-score", "--mode", "direct", "--model", "unused",
                                      "--revision", "unused", "--input", str(source),
                                      "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "Output must be new" in capsys.readouterr().err
    assert output.read_text() == "already here"


def test_empty_input_is_refused_before_loading(tmp_path, monkeypatch, capsys):
    source, output = tmp_path / "input.jsonl", tmp_path / "output.jsonl"
    source.write_text("\n")
    monkeypatch.setattr(sys, "argv", ["semif-score", "--mode", "direct", "--model", "unused",
                                      "--revision", "unused", "--input", str(source),
                                      "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "Input is empty" in capsys.readouterr().err
    assert not output.exists()
