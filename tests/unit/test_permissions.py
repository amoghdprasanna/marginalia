"""The setup check: which checks appear, how they read, and what fixing them does."""

import sys
from dataclasses import replace

import pytest
from helpers import FakeProbes

from marginalia import permissions
from marginalia.permissions import MISSING, OFF, OK, UNKNOWN, Fixer, host_app, needs_attention, run_checks


@pytest.fixture
def mac(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")


def by_key(checks):
    return {c.key: c for c in checks}


def test_all_good_needs_no_attention(mac, cfg):
    cfg = replace(cfg, voice_enabled=True)
    checks = by_key(run_checks(cfg, FakeProbes()))
    assert checks["api_key"].status == OK and checks["screen"].status == OK
    assert checks["microphone"].status == OK
    assert not needs_attention(list(checks.values()))


def test_missing_screen_recording_names_the_terminal(mac, cfg):
    checks = by_key(run_checks(cfg, FakeProbes(screen=False)))
    screen = checks["screen"]
    assert screen.status == MISSING and screen.action and "iTerm" in screen.detail
    assert needs_attention(list(checks.values()))


def test_an_unanswerable_screen_check_still_offers_the_fix(mac, cfg):
    assert by_key(run_checks(cfg, FakeProbes(screen=None)))["screen"].status == UNKNOWN


def test_no_api_key_needs_attention_unless_in_demo(mac, cfg):
    no_key = replace(cfg, api_key=None)
    assert by_key(run_checks(no_key, FakeProbes()))["api_key"].status == MISSING
    assert needs_attention(run_checks(no_key, FakeProbes()))
    demo = replace(no_key, demo=True)
    assert not needs_attention(run_checks(demo, FakeProbes()))


def test_the_key_check_names_the_chosen_provider(mac, cfg):
    gem = replace(cfg, provider="gemini", sources={"api_key": "env"})
    check = by_key(run_checks(gem, FakeProbes()))["api_key"]
    assert check.title == "Gemini API key" and check.status == OK and "GEMINI_API_KEY" in check.detail


def test_a_provider_without_its_library_needs_attention(mac, cfg, monkeypatch):
    from marginalia.providers import Provider

    monkeypatch.setattr(Provider, "installed", lambda self: False)
    check = by_key(run_checks(replace(cfg, provider="openai"), FakeProbes()))["api_key"]
    assert check.status == MISSING and 'marginalia[openai]' in check.detail and check.action == "Open Settings"


@pytest.mark.parametrize(
    ("mic", "status", "action"),
    [("not_determined", MISSING, "Allow…"), ("denied", MISSING, "Open Settings…"), ("unknown", UNKNOWN, None)],
)
def test_microphone_states(mac, cfg, mic, status, action):
    check = by_key(run_checks(replace(cfg, voice_enabled=True), FakeProbes(mic=mic)))["microphone"]
    assert (check.status, check.action) == (status, action)
    assert not check.required, "voice is optional; it never forces the window open"


def test_voice_off_or_not_installed(mac, cfg):
    assert by_key(run_checks(cfg, FakeProbes()))["microphone"].status == OFF
    on = replace(cfg, voice_enabled=True)
    check = by_key(run_checks(on, FakeProbes(), voice_problem="faster-whisper is not installed"))["microphone"]
    assert check.status == MISSING and "faster-whisper" in check.detail


def test_ocr_row_only_when_ocr_is_on(cfg):
    assert "ocr" not in by_key(run_checks(cfg, FakeProbes()))
    assert by_key(run_checks(cfg, FakeProbes(), ocr_available=False))["ocr"].status == OFF


def test_no_screen_row_off_macos_except_wayland(monkeypatch, cfg):
    monkeypatch.setattr(sys, "platform", "win32")
    assert "screen" not in by_key(run_checks(cfg, FakeProbes()))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert "portal" in by_key(run_checks(cfg, FakeProbes()))["screen"].detail


def test_host_app(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    assert host_app() == "Terminal"
    monkeypatch.delenv("TERM_PROGRAM")
    assert host_app() == "your terminal app"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert host_app() == "Marginalia"


def test_fixer(mac, cfg):
    probes, opened = FakeProbes(screen=False, mic="not_determined"), []
    fixer = Fixer(probes, lambda: opened.append("settings"))
    checks = by_key(run_checks(replace(cfg, api_key=None, voice_enabled=True), probes))
    fixer.fix(checks["screen"])
    # A stale entry from an earlier build is cleared first, or the system never asks again.
    assert probes.requested == ["forget screen", "screen"] and probes.opened == ["screen"]
    fixer.fix(checks["microphone"])
    assert probes.requested[-1] == "microphone"
    fixer.fix(checks["api_key"])
    assert opened == ["settings"]


def test_denied_microphone_opens_the_privacy_pane(mac, cfg):
    probes = FakeProbes(mic="denied")
    check = by_key(run_checks(replace(cfg, voice_enabled=True), probes))["microphone"]
    Fixer(probes).fix(check)
    assert probes.opened == ["microphone"]


def test_only_the_packaged_app_forgets_its_screen_recording_entry(monkeypatch):
    calls = []
    monkeypatch.delattr(sys, "frozen", raising=False)
    permissions.MacProbes().forget_screen_recording(run=lambda cmd, **kw: calls.append(cmd))
    assert calls == []  # from a terminal it would be the terminal's grant
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    permissions.MacProbes().forget_screen_recording(run=lambda cmd, **kw: calls.append(cmd))
    assert calls == [["tccutil", "reset", "ScreenCapture", permissions.BUNDLE_ID]]


@pytest.mark.skipif(sys.platform != "darwin", reason="asks macOS itself")
def test_mac_probes_answer_without_raising():
    p = permissions.MacProbes()
    assert p.screen_recording() in (True, False, None)
    assert p.microphone() in ("authorized", "denied", "not_determined", "restricted", "unknown")


@pytest.mark.skipif(sys.platform != "darwin", reason="asks macOS itself")
def test_the_microphone_request_knows_its_completion_handler_is_a_block():
    """Bug: the setup check's microphone button failed with "Argument 3 is a block, but no
    signature available". Checked without calling it, which would ask for the microphone."""
    device = permissions.MacProbes()._capture_device()
    handler = device.requestAccessForMediaType_completionHandler_.__metadata__()["arguments"][3]
    assert handler.get("callable", {}).get("arguments", ())[1]["type"] == b"Z"


# Windows ---------------------------------------------------------------------------------------


def registry(values):
    return lambda hive, path, name: values.get((hive, path.rsplit("\\", 1)[-1]))


@pytest.mark.parametrize(
    ("values", "status"),
    [
        ({("HKCU", "microphone"): "Allow", ("HKCU", "NonPackaged"): "Allow"}, "authorized"),
        ({("HKCU", "microphone"): "Allow", ("HKCU", "NonPackaged"): "Deny"}, "denied"),  # desktop apps off
        ({("HKLM", "microphone"): "Deny", ("HKCU", "microphone"): "Allow"}, "denied"),  # off for the machine
        ({}, "unknown"),
    ],
)
def test_windows_microphone_consent(values, status):
    assert permissions.WindowsProbes(registry(values)).microphone() == status


def test_windows_registry_path_points_at_the_microphone_store():
    seen = []
    permissions.WindowsProbes(lambda h, p, n: seen.append(p)).microphone()
    assert seen[0].endswith(r"ConsentStore\microphone") and seen[2].endswith(r"microphone\NonPackaged")


def test_default_probes_per_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert isinstance(permissions.default_probes(), permissions.WindowsProbes)
    monkeypatch.setattr(sys, "platform", "linux")
    assert type(permissions.default_probes()) is permissions.NoProbes


def test_fixing_the_microphone_leaves_screen_recording_alone(mac, cfg):
    probes = FakeProbes(mic="not_determined")
    Fixer(probes).fix(by_key(run_checks(replace(cfg, voice_enabled=True), probes))["microphone"])
    assert "forget screen" not in probes.requested


def test_forgetting_screen_recording_never_raises_or_hangs(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    seen = {}

    def broken(cmd, **kw):
        seen.update(kw)
        raise OSError("no tccutil")

    permissions.MacProbes().forget_screen_recording(run=broken)
    assert seen.get("timeout"), "a stuck tccutil must not freeze the setup window"
    assert seen.get("check") is False, "a failed reset still goes on to ask"
