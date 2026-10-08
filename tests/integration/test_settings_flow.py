"""Changing settings while the app runs: only what changed is rebuilt, and hotkeys pause to be recorded."""

from dataclasses import replace

import pytest
from helpers import FakeBrain, build
from PySide6.QtWidgets import QApplication

import marginalia.app as app_module
from marginalia.app import Factories


class Counting:
    def __init__(self, make):
        self.make, self.calls = make, 0

    def __call__(self, cfg):
        self.calls += 1
        return self.make(cfg)


@pytest.fixture
def factories():
    return Factories(
        brain=Counting(lambda c: FakeBrain(text=f"answer from {c.model}")),
        ocr=Counting(lambda c: None),
        transcriber=Counting(lambda c: None),
    )


@pytest.fixture
def hotkeys(monkeypatch):
    made = []

    class Hk:
        def __init__(self, bindings):
            self.bindings, self.stopped = bindings, False
            made.append(self)

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(app_module, "start_hotkeys", Hk)
    return made


def test_a_new_model_gets_a_new_brain_and_nothing_else(qtbot, cfg, factories):
    c = build(qtbot, cfg, factories=factories)
    c.apply_config(replace(cfg, model="claude-sonnet-5-5"))
    assert factories.brain.calls == 1 and factories.ocr.calls == 0 and factories.transcriber.calls == 0
    assert c.brain.text == "answer from claude-sonnet-5-5"


def test_saving_in_the_window_applies_at_once(qtbot, cfg, factories, caplog):
    c = build(qtbot, cfg, factories=factories)
    c.open_settings()
    w = c.settings_window
    qtbot.addWidget(w)
    w.fields["model"].setCurrentText("claude-haiku-5-5")
    w.fields["log_dir"].setText(str(cfg.log_dir))
    w.save()
    assert c.cfg.model == "claude-haiku-5-5" and c.brain.text == "answer from claude-haiku-5-5"
    assert "Settings applied" in caplog.text


def test_command_line_switches_survive_a_reload(qtbot, cfg, factories):
    c = build(qtbot, cfg, factories=factories)
    c.cfg.sources["ocr_enabled"] = "command line"
    c.store.save({"ocr_enabled": True, "log_dir": str(cfg.log_dir)})
    c.reload_settings()
    assert not c.cfg.ocr_enabled, "--no-ocr still wins"


def test_turning_voice_on_rebuilds_the_transcriber_and_the_buttons(qtbot, cfg):
    from helpers import FakeWhisper

    from marginalia.voice import Transcriber

    made = Factories(
        brain=lambda c: FakeBrain(),
        ocr=lambda c: None,
        transcriber=lambda c: Transcriber(c.whisper_model, model_factory=lambda n: FakeWhisper(), problem=None)
        if c.voice_enabled
        else None,
    )
    c = build(qtbot, cfg, factories=made)
    assert not c.chooser.voice_btn.isEnabled()
    c.apply_config(replace(cfg, voice_enabled=True))
    assert c.transcriber is not None and c.chooser.voice_btn.isEnabled()
    assert c.askbox.mic.isVisibleTo(c.askbox)


def test_hotkeys_pause_while_settings_are_open_and_come_back(qtbot, cfg, hotkeys):
    cfg.hotkey_enabled = True
    c = build(qtbot, cfg)
    c.start()
    first = hotkeys[-1]
    c.open_settings()
    qtbot.addWidget(c.settings_window)
    assert first.stopped and c.hotkey is None, "else the window couldn't record the same combo"
    c.settings_window.close()
    assert c.hotkey is not None and c.hotkey is not first
    c.stop()


def test_new_shortcuts_are_registered_and_shown(qtbot, cfg, hotkeys):
    c = build(qtbot, cfg)
    c.apply_config(replace(cfg, hotkey="<ctrl>+<shift>+k", hotkey_enabled=True))
    assert hotkeys[-1].bindings[0][0] == "<ctrl>+<shift>+k"
    assert "K" in c.orb.toolTip()
    c.stop()


def test_orb_menu_opens_settings(qtbot, cfg):
    c = build(qtbot, cfg)
    actions = {a.text(): a for a in c.orb.build_menu().actions() if a.text()}
    actions["Settings…"].trigger()
    qtbot.addWidget(c.settings_window)
    assert c.settings_window.isVisible()
    QApplication.processEvents()


# the setup check -------------------------------------------------------------------------------


def test_first_run_shows_the_setup_check_once(qtbot, cfg):
    c = build(qtbot, cfg)
    c.maybe_show_setup()
    qtbot.addWidget(c.setup_window)
    assert c.setup_window.isVisible()
    c.setup_window.close()
    assert not c.store.first_run()
    c.setup_window = None
    c.maybe_show_setup()
    assert c.setup_window is None, "all good and seen before: not shown again"


def test_a_missing_permission_shows_it_even_later(qtbot, cfg, monkeypatch):
    from helpers import FakeProbes

    monkeypatch.setattr("sys.platform", "darwin")
    c = build(qtbot, cfg, probes=FakeProbes(screen=False))
    c.store.save({})  # not the first run
    c.maybe_show_setup()
    qtbot.addWidget(c.setup_window)
    assert "screen" in c.setup_window.buttons


def test_fixing_the_api_key_opens_settings_and_saving_rechecks(qtbot, cfg):
    cfg.api_key = None
    c = build(qtbot, cfg)
    c.open_setup()
    qtbot.addWidget(c.setup_window)
    c.setup_window.buttons["api_key"].click()
    qtbot.addWidget(c.settings_window)
    assert c.settings_window.isVisible()
    c.settings_window.key_edit.setText("sk-ant-api03-pasted-in-settings-window")
    c.settings_window.fields["log_dir"].setText(str(cfg.log_dir))
    c.settings_window.save()
    assert c.cfg.api_key == "sk-ant-api03-pasted-in-settings-window"
    assert "api_key" not in c.setup_window.buttons, "the setup check refreshed after saving"


def test_orb_menu_has_the_setup_check(qtbot, cfg):
    c = build(qtbot, cfg)
    actions = {a.text(): a for a in c.orb.build_menu().actions() if a.text()}
    actions["Setup check…"].trigger()
    qtbot.addWidget(c.setup_window)
    assert c.setup_window.isVisible()
