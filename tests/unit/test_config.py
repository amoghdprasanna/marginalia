from pathlib import Path

import pytest

from marginalia.config import load_config

VARS = [
    "ANTHROPIC_API_KEY",
    "MARGINALIA_MODEL",
    "MARGINALIA_HIRES",
    "MARGINALIA_HOTKEY",
    "MARGINALIA_HOTKEY_ENABLED",
    "MARGINALIA_OCR",
    "MARGINALIA_LOG_DIR",
    "MARGINALIA_DEMO",
    "MARGINALIA_USER_CONTEXT",
    "MARGINALIA_MAX_TOKENS",
    "MARGINALIA_EFFORT",
    "MARGINALIA_VOICE",
    "MARGINALIA_WHISPER_MODEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in VARS:
        monkeypatch.delenv(v, raising=False)


def test_defaults():
    c = load_config()
    assert c.api_key is None
    assert c.model == "claude-opus-5-5"
    assert c.effort == "medium" and c.max_tokens == 16000
    assert c.hotkey_enabled and c.ocr_enabled and c.voice_enabled
    assert not c.demo and not c.hires
    assert c.log_dir == Path.home() / "Marginalia"


@pytest.mark.parametrize("value,expected", [("1", True), ("yes", True), ("ON", True), ("0", False), ("nope", False)])
def test_flags(monkeypatch, value, expected):
    monkeypatch.setenv("MARGINALIA_HIRES", value)
    assert load_config().hires is expected


def test_command_line_switches_override_env(monkeypatch):
    monkeypatch.setenv("MARGINALIA_OCR", "1")
    c = load_config(demo=True, no_hotkey=True, no_ocr=True, no_voice=True)
    assert c.demo and not c.hotkey_enabled and not c.ocr_enabled and not c.voice_enabled


def test_env_values(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("MARGINALIA_EFFORT", "low")
    monkeypatch.setenv("MARGINALIA_LOG_DIR", str(tmp_path))
    c = load_config()
    assert c.api_key == "sk-test" and c.effort == "low" and c.log_dir == tmp_path


def test_a_bad_number_falls_back_to_the_default_instead_of_crashing(monkeypatch, capsys):
    """Bug: MARGINALIA_MAX_TOKENS=16k stopped the app at startup with a ValueError traceback."""
    monkeypatch.setenv("MARGINALIA_MAX_TOKENS", "16k")
    assert load_config().max_tokens == 16000
    assert "MARGINALIA_MAX_TOKENS" in capsys.readouterr().out


def test_an_unknown_effort_falls_back_to_medium(monkeypatch, capsys):
    """Bug: a typo here made every single question fail with an API error."""
    monkeypatch.setenv("MARGINALIA_EFFORT", "hihg")
    assert load_config().effort == "medium"
    assert "MARGINALIA_EFFORT" in capsys.readouterr().out
