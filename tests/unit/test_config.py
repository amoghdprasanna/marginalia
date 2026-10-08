from pathlib import Path

import pytest
from helpers import FakeKeyring

from marginalia.config import SETTINGS, SettingsStore, load_config, settings_path
from marginalia.secrets import Keychain

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
    "MARGINALIA_VOICE_HOTKEY",
    "MARGINALIA_SAVE_CASES",
    "MARGINALIA_LOG_LEVEL",
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


def test_a_bad_number_falls_back_to_the_default_instead_of_crashing(monkeypatch, caplog):
    """Bug: MARGINALIA_MAX_TOKENS=16k stopped the app at startup with a ValueError traceback."""
    monkeypatch.setenv("MARGINALIA_MAX_TOKENS", "16k")
    assert load_config().max_tokens == 16000
    assert "MARGINALIA_MAX_TOKENS" in caplog.text


def test_an_unknown_effort_falls_back_to_medium(monkeypatch, caplog):
    """Bug: a typo here made every single question fail with an API error."""
    monkeypatch.setenv("MARGINALIA_EFFORT", "hihg")
    assert load_config().effort == "medium"
    assert "MARGINALIA_EFFORT" in caplog.text



# the settings file -------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    return SettingsStore(tmp_path / "settings.json")


def test_settings_file_values_are_used(store):
    store.save({"model": "claude-sonnet-5-5", "effort": "low", "ocr_enabled": False})
    c = load_config(store=store)
    assert (c.model, c.effort, c.ocr_enabled) == ("claude-sonnet-5-5", "low", False)
    assert c.sources["model"] == "settings" and c.sources["hotkey"] == "default"


def test_environment_beats_the_settings_file(store, monkeypatch):
    store.save({"effort": "low"})
    monkeypatch.setenv("MARGINALIA_EFFORT", "high")
    c = load_config(store=store)
    assert c.effort == "high" and c.sources["effort"] == "env"


def test_command_line_beats_both(store, monkeypatch):
    store.save({"ocr_enabled": True})
    monkeypatch.setenv("MARGINALIA_OCR", "1")
    c = load_config(no_ocr=True, store=store)
    assert not c.ocr_enabled and c.sources["ocr_enabled"] == "command line"


def test_a_bad_value_in_the_settings_file_falls_back(store, caplog):
    store.save({"max_tokens": "lots", "effort": "extreme", "log_dir": "~/Notes"})
    c = load_config(store=store)
    assert c.max_tokens == 16000 and c.effort == "medium"
    assert c.log_dir == Path.home() / "Notes", "paths expand ~"
    assert "settings max_tokens" in caplog.text


def test_a_corrupt_settings_file_is_ignored_not_fatal(store, caplog):
    store.path.write_text("{not json")
    assert load_config(store=store).model == "claude-opus-5-5"
    assert "Ignoring the settings file" in caplog.text


def test_saving_merges_and_keeps_unknown_keys(store):
    store.save({"model": "a", "from_a_newer_version": 1})
    store.save({"effort": "high"})
    assert store.load() == {"model": "a", "effort": "high", "from_a_newer_version": 1}
    assert not store.path.with_suffix(".tmp").exists()


def test_first_run_is_when_there_is_no_settings_file(store):
    assert store.first_run()
    store.save({})
    assert not store.first_run()


def test_settings_path_is_per_platform(monkeypatch):
    monkeypatch.delenv("MARGINALIA_SETTINGS_FILE")
    monkeypatch.setattr("sys.platform", "darwin")
    assert settings_path().parts[-4:] == ("Library", "Application Support", "Marginalia", "settings.json")
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg")
    assert settings_path() == Path("/xdg/marginalia/settings.json")
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", "C:/Users/me/AppData/Roaming")
    assert settings_path() == Path("C:/Users/me/AppData/Roaming/Marginalia/settings.json")


def test_every_setting_has_a_distinct_env_var():
    assert len({s.env for s in SETTINGS}) == len(SETTINGS)
    assert all(s.env.startswith("MARGINALIA_") for s in SETTINGS)


# the API key ---------------------------------------------------------------------------------


def test_api_key_comes_from_the_keychain_when_the_environment_has_none(store):
    kc = Keychain(FakeKeyring())
    kc.set("sk-ant-from-keychain")
    c = load_config(store=store, keychain=kc)
    assert c.api_key == "sk-ant-from-keychain" and c.sources["api_key"] == "keychain"


def test_api_key_in_the_environment_wins(store, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    kc = Keychain(FakeKeyring())
    kc.set("sk-keychain")
    c = load_config(store=store, keychain=kc)
    assert c.api_key == "sk-env" and c.sources["api_key"] == "env"


def test_a_broken_keychain_means_no_key_not_a_crash(store):
    c = load_config(store=store, keychain=Keychain(FakeKeyring(error=RuntimeError("locked"))))
    assert c.api_key is None and c.sources["api_key"] == "none"
