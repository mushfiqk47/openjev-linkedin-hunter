import tempfile
from pathlib import Path
from linkedin_connect.ledger import ConnectLedger, norm_name, profile_slug

def test_profile_slug():
    assert profile_slug("https://www.linkedin.com/in/john-doe-123/") == "john-doe-123"
    assert profile_slug("https://linkedin.com/in/jane-doe?miniProfileUrn=xyz") == "jane-doe"
    assert profile_slug("john-doe-456") == "john-doe-456"
    assert profile_slug("") == ""

def test_norm_name():
    assert norm_name("John Doe, Ph.D.") == "john doe ph d"
    assert norm_name("  Jane   Smith  ") == "jane smith"

def test_ledger_records_and_restricts(tmp_path, monkeypatch):
    reg_file = tmp_path / "connect_registry.json"
    audit_file = tmp_path / "Connects.md"
    restr_file = tmp_path / "restricted.txt"
    restr_file.write_text("Blocked Boss\nblocked-slug\n", encoding="utf-8")

    monkeypatch.setattr("linkedin_connect.ledger.REGISTRY_FILE", reg_file)
    monkeypatch.setattr("linkedin_connect.ledger.LEDGER_FILE", audit_file)
    monkeypatch.setattr("linkedin_connect.ledger.LOCAL_RESTRICTED_FILE", restr_file)
    monkeypatch.setattr("linkedin_connect.ledger.OUTREACH_RESTRICTED_FILE", tmp_path / "none.txt")
    monkeypatch.setattr("linkedin_connect.ledger.OUTREACH_REGISTRY_FILE", tmp_path / "none_reg.json")

    ledger = ConnectLedger()

    # Verify restriction checks
    assert ledger.is_restricted("Blocked Boss", "https://linkedin.com/in/some-other-slug") is True
    assert ledger.is_restricted("Allowed Person", "https://linkedin.com/in/blocked-slug") is True
    assert ledger.is_restricted("Allowed Person", "https://linkedin.com/in/allowed-slug") is False

    # Record sent
    ledger.record_sent("Alice Lead", "https://linkedin.com/in/alice-lead", "Head of Design", "design_leader", 92, "Sent test")
    assert ledger.is_handled("https://linkedin.com/in/alice-lead") is True
    assert ledger.get_today_sent_count() == 1

    # Check persistence
    ledger2 = ConnectLedger()
    assert ledger2.is_handled("https://linkedin.com/in/alice-lead") is True
    assert audit_file.exists()
    content = audit_file.read_text(encoding="utf-8")
    assert "Alice Lead" in content
    assert "design_leader" in content
