"""Starting up: the global hotkey, the ready message, warming the speech model, and the command line."""

import sys
from types import ModuleType, SimpleNamespace

import pytest
from helpers import FakeBrain, FakeOCR, FakeWhisper, ManualExecutor, build, make_snapshot
from PySide6.QtWidgets import QApplication

from marginalia import app as app_module
from marginalia.app import default_services, start_hotkey
from marginalia.brain import ClaudeBrain, DemoBrain
from marginalia.voice import Transcriber

# the global hotkey -----------------------------------------------------------------------------


class FakeHotKeys:
    """Stands in for pynput.keyboard.GlobalHotKeys."""

    instances: list = []

    def __init__(self, mapping):
        self.mapping, self.daemon, self.started = mapping, False, False
        FakeHotKeys.instances.append(self)

    def start(self):
        self.started = True


@pytest.fixture
def fake_pynput(monkeypatch):
    FakeHotKeys.instances = []
    pynput = ModuleType("pynput")
    pynput.keyboard = SimpleNamespace(GlobalHotKeys=FakeHotKeys)
    monkeypatch.setitem(sys.modules, "pynput", pynput)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    return FakeHotKeys


def test_hotkey_is_registered_on_a_daemon_thread(fake_pynput):
    callback = object()
    listener = start_hotkey("<ctrl>+<alt>+<space>", callback)
    assert listener is fake_pynput.instances[0]
    assert listener.mapping == {"<ctrl>+<alt>+<space>": callback}
    assert listener.started and listener.daemon, "a daemon thread must not keep the app alive on quit"


def test_hotkey_is_skipped_on_wayland_with_a_reason(fake_pynput, monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert start_hotkey("<ctrl>+<alt>+<space>", lambda: None) is None
    assert fake_pynput.instances == []
    assert "Wayland" in capsys.readouterr().out


def test_hotkey_failure_falls_back_to_the_orb(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "pynput", None)  # import fails, as with a blocked keyboard hook
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert start_hotkey("<ctrl>+<alt>+<space>", lambda: None) is None
    assert "Use the orb" in capsys.readouterr().out


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


def test_ready_message_says_what_is_on(started, capsys):
    c = started()
    c.start()
    out = capsys.readouterr().out
    assert "Ready (claude-opus-5-5, OCR off, voice off, trigger: orb only)" in out
    assert str(c.log.dir) in out
    assert c.orb.isVisible()


def test_speech_model_is_loaded_in_the_background_at_start(started):
    loads = []
    c = started()
    c.transcriber = Transcriber("tiny.en", model_factory=lambda n: loads.append(n) or FakeWhisper(), problem=None)
    c.start()
    assert loads == ["tiny.en"], "warmed once at start, so the first spoken question is not slow"


def test_speech_model_that_fails_to_load_is_reported_not_raised(started, capsys):
    def broken(name):
        raise OSError("disk full")

    c = started()
    c.transcriber = Transcriber("tiny.en", model_factory=broken, problem=None)
    c.start()
    assert "Could not load the speech model 'tiny.en': disk full" in capsys.readouterr().out


def test_missing_extras_are_explained_at_start(started, capsys):
    c = started(ocr=FakeOCR(available=False))
    c.transcriber = Transcriber("tiny.en", problem="faster-whisper is not installed")
    c.start()
    out = capsys.readouterr().out
    assert "Voice not installed (faster-whisper is not installed)" in out
    assert "OCR not installed" in out


def test_stop_releases_the_hotkey_timer_and_microphone(started, cfg, fake_pynput):
    cfg.hotkey_enabled = True
    c = started()
    c.start()
    hook = c.hotkey
    stopped = []
    hook.stop = lambda: stopped.append(True)
    c.recorder.start()
    c.stop()
    assert stopped and c.hotkey is None
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
def fake_main(monkeypatch, qapp):
    """Run main() without a real controller, event loop, or touching the test runner's Ctrl+C."""
    made = []

    class FakeController:
        def __init__(self, cfg):
            self.cfg, self.started = cfg, False
            made.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(app_module, "Controller", FakeController)
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


def test_missing_api_key_is_pointed_out(fake_main, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MARGINALIA_DEMO", raising=False)
    with pytest.raises(SystemExit):
        app_module.main([])
    assert "No ANTHROPIC_API_KEY found" in capsys.readouterr().out


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
