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
    assert probes.requested == ["screen"] and probes.opened == ["screen"]
    fixer.fix(checks["microphone"])
    assert probes.requested[-1] == "microphone"
    fixer.fix(checks["api_key"])
    assert opened == ["settings"]


def test_denied_microphone_opens_the_privacy_pane(mac, cfg):
    probes = FakeProbes(mic="denied")
    check = by_key(run_checks(replace(cfg, voice_enabled=True), probes))["microphone"]
    Fixer(probes).fix(check)
    assert probes.opened == ["microphone"]


@pytest.mark.skipif(sys.platform != "darwin", reason="asks macOS itself")
def test_mac_probes_answer_without_raising():
    p = permissions.MacProbes()
    assert p.screen_recording() in (True, False, None)
    assert p.microphone() in ("authorized", "denied", "not_determined", "restricted", "unknown")
