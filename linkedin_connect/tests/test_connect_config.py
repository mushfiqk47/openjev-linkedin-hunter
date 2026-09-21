from pathlib import Path
from linkedin_connect.config import (
    DAILY_CONNECT_LIMIT,
    MIN_CONNECT_SCORE,
    TARGET_QUERIES,
    CONNECT_DELAY,
    SCROLL_DELAY,
    get_bool,
    get_int,
    get_str,
)

def test_config_defaults():
    assert DAILY_CONNECT_LIMIT >= 1
    assert MIN_CONNECT_SCORE >= 50
    assert len(TARGET_QUERIES) >= 3
    assert CONNECT_DELAY >= 0.0
    assert SCROLL_DELAY >= 0.0

def test_get_helpers(monkeypatch):
    monkeypatch.setenv("TEST_INT", "42")
    monkeypatch.setenv("TEST_BOOL", "true")
    monkeypatch.setenv("TEST_STR", "  hello  ")

    assert get_int("TEST_INT", 10) == 42
    assert get_bool("TEST_BOOL", False) is True
    assert get_str("TEST_STR", "def") == "hello"
    assert get_int("NON_EXISTENT", 99) == 99
    assert get_bool("NON_EXISTENT", False) is False
