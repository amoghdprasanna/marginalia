"""Starting up: the global hotkey, the ready message, warming the speech model, and the command line."""

import sys

import pytest
from helpers import FakeBrain, FakeOCR, FakeWhisper, ManualExecutor, build, make_snapshot
from PySide6.QtWidgets import QApplication

from marginalia import app as app_module
from marginalia.app import default_services
from marginalia.brain import ClaudeBrain, DemoBrain
from marginalia.voice import Transcriber

# the global hotkeys ----------------------------------------------------------------------------


class FakeHotkeys:
    """What hotkeys.start_hotkeys returns: something with stop()."""

    def __init__(self, bindings):
        self.bindings, self.stopped = bindings, False

    def stop(self):
        self.stopped = True


@pytest.fixture
def fake_hotkeys(monkeypatch):
    made = []
    monkeypatch.setattr(app_module, "start_hotkeys", lambda b: made.append(FakeHotkeys(b)) or made[-1])
    return made


def test_start_binds_the_ask_and_hold_to_talk_keys(started, cfg, fake_hotkeys):
    cfg.hotkey_enabled = True
    c = started()
    c.start()
    [hk] = fake_hotkeys
    assert [b[0] for b in hk.bindings] == [cfg.hotkey, cfg.voice_hotkey]
    assert hk.bindings[0][2] is None, "the ask key acts on press only"
    assert hk.bindings[1][2] is not None, "the voice key also needs its release"


def test_an_empty_voice_hotkey_binds_only_the_ask_key(started, cfg, fake_hotkeys):
    cfg.hotkey_enabled, cfg.voice_hotkey = True, ""
    started().start()
    assert len(fake_hotkeys[0].bindings) == 1


def test_no_hotkey_binds_nothing(started, cfg, fake_hotkeys):
    started().start()
    assert fake_hotkeys == []


def test_hotkey_asks_about_exactly_where_the_mouse_is(qtbot, cfg):
    c = build(qtbot, cfg)
    c.rest.rest = (5, 5)  # the orb would ask here; the hotkey must not
    seen = []

    def grab(x, y):
        seen.append((x, y))
        return make_snapshot(cursor=(x, y))

    c.grab = grab
    c.bus.hotkey.emit()
    qtbot.waitUntil(c.askbox.isVisible)
    assert seen and seen[0] != (5, 5)


@pytest.fixture
def started(qtbot, cfg):
    """A controller after start(); stopped again before qtbot deletes its windows."""
    made = []

    def start(**kw):
        c = build(qtbot, cfg, **kw)
        made.append(c)
        return c

    yield start
    for c in made:
        c.stop()


# start() and stop() --------------------------------------------------------------------------------------


def test_ready_message_says_what_is_on(started, caplog):
    c = started()
    c.start()
    out = caplog.text
    assert "Ready (claude-opus-5-5, OCR off, voice off, trigger: orb only)" in out
    assert str(c.log.dir) in out
    assert c.orb.isVisible()


def test_speech_model_is_loaded_in_the_background_at_start(started):
    loads = []
    c = started()
    c.transcriber = Transcriber("tiny.en", model_factory=lambda n: loads.append(n) or FakeWhisper(), problem=None)
    c.start()
    assert loads == ["tiny.en"], "warmed once at start, so the first spoken question is not slow"


def test_speech_model_that_fails_to_load_is_reported_not_raised(started, caplog):
    def broken(name):
        raise OSError("disk full")

    c = started()
    c.transcriber = Transcriber("tiny.en", model_factory=broken, problem=None)
    c.start()
    assert "Could not load the speech model 'tiny.en': disk full" in caplog.text


def test_missing_extras_are_explained_at_start(started, caplog):
    c = started(ocr=FakeOCR(available=False))
    c.transcriber = Transcriber("tiny.en", problem="faster-whisper is not installed")
    c.start()
    out = caplog.text
    assert "Voice not installed (faster-whisper is not installed)" in out
    assert "OCR not installed" in out


def test_stop_releases_the_hotkey_timer_and_microphone(started, cfg, fake_hotkeys):
    cfg.hotkey_enabled = True
    c = started()
    c.start()
    c.recorder.start()
    c.stop()
    assert fake_hotkeys[0].stopped and c.hotkey is None
    assert not c._poll.isActive()
    assert not c.recorder.recording


def test_stop_cancels_an_answer_in_flight(qtbot, cfg):
    pool = ManualExecutor()
    brain = FakeBrain(partials=["a", "ab"])
    c = build(qtbot, cfg, brain=brain, pool=pool)
    c.snapshot = make_snapshot()
    c.ask("q")
    c.stop()
    pool.run_all()
    assert brain.delivered == [] and c.history == []


def test_voice_buttons_reflect_whether_voice_works(qtbot, cfg):
    c = build(qtbot, cfg)
    assert not c.chooser.voice_btn.isEnabled()
    assert "disabled in settings" in c.chooser.voice_btn.toolTip()
    assert not c.askbox.mic.isVisibleTo(c.askbox)


# default services and the command line ----------------------------------------------------------


def test_default_services_follow_the_config(cfg):
    sv = default_services(cfg)
    assert isinstance(sv.brain, ClaudeBrain)
    assert sv.ocr is None and sv.transcriber is None, "both are off in the test config"
    cfg.demo = True
    assert isinstance(default_services(cfg).brain, DemoBrain)


@pytest.fixture
def fake_main(monkeypatch, qapp, tmp_path):
    """Run main() without a real controller, event loop, or touching the test runner's Ctrl+C."""
    made = []
    monkeypatch.setenv("MARGINALIA_LOG_DIR", str(tmp_path))  # main opens a log file there

    class FakeController:
        def __init__(self, cfg):
            self.cfg, self.started = cfg, False
            made.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        def maybe_show_setup(self):
            self.setup_checked = True

        def offer_crash_reports(self, reporter):
            self.reporter = reporter

        def check_for_updates(self):
            self.update_checked = True

    class FakeReporter:
        def __init__(self, log_dir):
            self.installed = self.collected = False

        def install(self):  # the real one would hook the test runner's excepthook
            self.installed = True

        def collect_fatal(self):
            self.collected = True

    monkeypatch.setattr(app_module, "Controller", FakeController)
    monkeypatch.setattr(app_module, "CrashReporter", FakeReporter)
    monkeypatch.setattr(QApplication, "exec", lambda *a: 7)
    monkeypatch.setattr(app_module.signal, "signal", lambda *a: None)
    monkeypatch.setattr(app_module, "hard_exit", lambda code: sys.exit(code))
    return made


def test_command_line_flags_reach_the_config(fake_main):
    with pytest.raises(SystemExit) as exit_:
        app_module.main(["--demo", "--no-hotkey", "--no-ocr", "--no-voice"])
    [c] = fake_main
    assert c.started
    QApplication.instance().aboutToQuit.emit()
    assert c.stopped, "quitting stops the controller (hotkey hook, mic)"
    assert c.cfg.demo and not c.cfg.hotkey_enabled and not c.cfg.ocr_enabled and not c.cfg.voice_enabled
    assert exit_.value.code == 7, "the process exits with the event loop's status"


def test_missing_api_key_is_pointed_out(fake_main, monkeypatch, caplog):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MARGINALIA_DEMO", raising=False)
    with pytest.raises(SystemExit):
        app_module.main([])
    assert "No API key found" in caplog.text


def test_quitting_does_not_wait_for_busy_workers(fake_main, monkeypatch):
    """Bug: quit hung until a speech-model download or a still-thinking answer finished.

    sys.exit joins every ThreadPoolExecutor worker first. Nothing a worker holds needs saving
    (the journal is written on the main thread), so main ends the process directly.
    """
    exits = []

    def record(code):
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(app_module, "hard_exit", record)
    with pytest.raises(SystemExit):
        app_module.main(["--demo"])
    assert exits == [7]


def test_stop_drops_queued_work(started):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    release = threading.Event()
    pool = ThreadPoolExecutor(max_workers=1)
    c = started(pool=pool)
    c.start()
    pool.submit(release.wait, 5)
    queued = pool.submit(lambda: "never needed")
    c.stop()
    release.set()
    assert queued.cancelled()


def test_main_keeps_a_json_log_in_the_log_folder(fake_main, tmp_path):
    with pytest.raises(SystemExit):
        app_module.main(["--demo"])
    assert (tmp_path / "logs" / "marginalia.jsonl").exists()


def test_main_installs_crash_reporting_and_offers_old_reports(fake_main):
    with pytest.raises(SystemExit):
        app_module.main(["--demo"])
    [c] = fake_main
    assert c.reporter.installed and c.reporter.collected


# crash reports ---------------------------------------------------------------------------------


@pytest.fixture
def crashed(tmp_path):
    from marginalia.crash import CrashReporter

    r = CrashReporter(tmp_path)
    r.dir.mkdir(parents=True)
    r._write({"type": "ValueError", "message": "singular", "traceback": "...", "handled": False})
    return r


def test_crash_reports_are_offered_only_when_opted_in(qtbot, cfg, crashed):
    c = build(qtbot, cfg)
    c.offer_crash_reports(crashed)
    assert c.notice is None, "off by default: nothing is offered"
    cfg.crash_reports = True
    c.offer_crash_reports(crashed)
    qtbot.addWidget(c.notice)
    assert "singular" in c.notice.text.text()


def test_reporting_opens_a_prefilled_issue_and_stops_asking(qtbot, cfg, crashed, monkeypatch):
    opened = []
    cfg.crash_reports = True
    c = build(qtbot, cfg)
    monkeypatch.setattr(c, "open_url", lambda url: opened.append(url.toString()))
    c.offer_crash_reports(crashed)
    qtbot.addWidget(c.notice)
    c.notice.buttons["Report…"].click()
    assert opened and "issues/new" in opened[0] and "singular" in opened[0]
    assert crashed.pending() == []


def test_not_now_also_stops_asking(qtbot, cfg, crashed):
    cfg.crash_reports = True
    c = build(qtbot, cfg)
    c.offer_crash_reports(crashed)
    qtbot.addWidget(c.notice)
    c.notice.buttons["Not now"].click()
    assert crashed.pending() == [] and not c.notice.isVisible()


# updates ---------------------------------------------------------------------------------------


def with_release(c, version="9.9.9"):
    from marginalia.updates import Release

    c.fetch_release = lambda: Release(version, "https://github.com/o/r/releases/tag/v" + version, "Notes.", {})


def test_a_newer_release_is_announced_once_and_stays_in_the_menu(qtbot, cfg):
    c = build(qtbot, cfg)
    with_release(c)
    c.check_for_updates()
    qtbot.addWidget(c.notice)
    assert c.notice.heading.text() == "Marginalia 9.9.9 is available"
    labels = [a.text() for a in c.orb.build_menu().actions()]
    assert "Update to 9.9.9…" in labels
    c.notice.close()
    c.notice = None
    c.state.save({"update_checked_at": "2000-01-01T00:00:00"})
    c.check_for_updates()
    assert c.notice is None, "the same version is announced once"


def test_checks_at_most_daily_and_never_when_off(qtbot, cfg):
    calls = []
    c = build(qtbot, cfg)
    c.fetch_release = lambda: calls.append(1)
    c.check_for_updates()
    c.check_for_updates()
    assert calls == [1]
    cfg.check_updates = False
    c.state.save({"update_checked_at": "2000-01-01T00:00:00"})
    c.check_for_updates()
    assert calls == [1]


def test_an_update_check_does_not_end_the_first_run(qtbot, cfg):
    c = build(qtbot, cfg)
    c.check_for_updates()
    assert c.store.first_run(), "bookkeeping lives in state.json, not the settings file"


def test_checking_by_hand_says_when_up_to_date(qtbot, cfg):
    c = build(qtbot, cfg)
    with_release(c, "0.0.1")
    c.orb.check_updates_requested.emit()
    qtbot.addWidget(c.notice)
    assert "latest version" in c.notice.text.text()


def test_download_opens_the_release(qtbot, cfg, monkeypatch):
    opened = []
    c = build(qtbot, cfg)
    monkeypatch.setattr(c, "open_url", lambda url: opened.append(url.toString()))
    with_release(c)
    c.check_for_updates()
    qtbot.addWidget(c.notice)
    c.notice.buttons["Download…"].click()
    assert opened == ["https://github.com/o/r/releases/tag/v9.9.9"]
