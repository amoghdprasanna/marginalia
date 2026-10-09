"""Asking by voice, end to end: record, transcribe, ask; and every way that can go wrong."""

import numpy as np
from helpers import (
    FakeBrain,
    ManualExecutor,
    build,
    make_snapshot,
)

from marginalia.voice import Recorder


def test_voice_question_end_to_end(qtbot, cfg):
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, voice_text="why is the distance odd")
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    assert c.recorder.recording
    c.streams[0].push(np.full(16000, 0.1, dtype=np.float32))
    c.listenbox._send()
    assert not c.recorder.recording
    assert brain.asked[0][0] == "why is the distance odd"
    assert not c.listenbox.isVisible() and c.bubble.isVisible()


def test_silence_is_not_sent_as_a_question(qtbot, cfg):
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, voice_text="")
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    c.streams[0].push(np.zeros(16000, dtype=np.float32))
    c.listenbox._send()
    assert brain.asked == [] and c.listenbox.status.text() == "Didn't catch that."


def test_cancel_stops_the_mic_and_drops_late_transcripts(qtbot, cfg):
    pool = ManualExecutor()
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, pool=pool, voice_text="late")
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    c.streams[0].push(np.full(16000, 0.1, dtype=np.float32))
    c.listenbox._send()
    c.listenbox.close_quietly()
    c._cancel_listening()
    pool.run_all()
    assert brain.asked == []


def test_mic_error_is_shown_not_raised(qtbot, cfg):
    def no_mic(cb):
        raise OSError("No input device")

    c = build(qtbot, cfg, voice_text="x")
    c.recorder = Recorder(stream_factory=no_mic)
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    assert "Microphone unavailable" in c.listenbox.status.text()


def test_without_voice_the_speak_path_falls_back_to_typing(qtbot, cfg):
    c = build(qtbot, cfg)  # no transcriber
    assert not c.chooser.voice_btn.isEnabled() and not c.askbox.mic.isVisibleTo(c.askbox)
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.askbox.isVisible)


def test_switching_from_typing_to_voice_reuses_the_screenshot(qtbot, cfg):
    grabs = []
    c = build(qtbot, cfg, voice_text="x", grab=lambda x, y: grabs.append(1) or make_snapshot(cursor=(x, y)))
    c.start_ask(at_cursor=False)
    qtbot.waitUntil(c.askbox.isVisible)
    c.askbox._to_voice()
    assert c.listenbox.isVisible() and len(grabs) == 1


def test_cancelling_a_spoken_follow_up_ends_the_thread_it_hid(qtbot, cfg):
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, voice_text="and this?")
    c.snapshot = make_snapshot()
    c.ask("first")
    c.bubble.voice_followup.emit()
    qtbot.waitUntil(c.listenbox.isVisible)
    c.listenbox.cancelled.emit()
    assert c.history == []


# hold to talk ----------------------------------------------------------------------------------


def test_holding_the_voice_key_listens_until_release(qtbot, cfg, monkeypatch):
    import marginalia.app as app_module

    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, voice_text="what is this term")
    c.bus.voice_down.emit()
    qtbot.waitUntil(c.listenbox.isVisible)
    assert c.listenbox.hold, "a pause must not end a held question"
    c.streams[0].push(np.full(16000, 0.1, dtype=np.float32))
    clock[0] += 2.0
    c.bus.voice_up.emit()
    assert brain.asked[0][0] == "what is this term"


def test_tapping_the_voice_key_listens_until_a_pause(qtbot, cfg, monkeypatch):
    import marginalia.app as app_module

    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, voice_text="x")
    c.bus.voice_down.emit()
    qtbot.waitUntil(c.listenbox.isVisible)
    clock[0] += 0.1
    c.bus.voice_up.emit()
    assert c.listenbox.isVisible() and not c.listenbox.hold
    assert brain.asked == [] and c.recorder.recording


def test_letting_go_during_the_capture_delay_counts_as_a_tap(qtbot, cfg):
    c = build(qtbot, cfg, voice_text="x")
    c.bus.voice_down.emit()
    c.bus.voice_up.emit()  # released before listening began
    qtbot.waitUntil(c.listenbox.isVisible)
    assert not c.listenbox.hold


def test_the_voice_key_types_when_voice_is_off(qtbot, cfg):
    c = build(qtbot, cfg)
    c.bus.voice_down.emit()
    qtbot.waitUntil(c.askbox.isVisible)
    c.bus.voice_up.emit()  # harmless


def test_voice_outcomes_are_logged_for_diagnosis(qtbot, cfg, caplog):
    c = build(qtbot, cfg, voice_text="")
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    c.streams[0].push(np.full(16000, 0.2, dtype=np.float32))
    c.listenbox._send()
    assert "recorded" in caplog.text and "Nothing was heard" in caplog.text
    assert "what does this mean" not in caplog.text, "never the words themselves"


def test_no_audio_says_which_microphone(qtbot, cfg, caplog):
    c = build(qtbot, cfg, voice_text="x")
    c.recorder._device_name = lambda: "iPhone (2) Microphone"
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    c.listenbox.no_audio.emit()
    assert "No sound from iPhone (2) Microphone" in c.listenbox.status.text()
    assert not c.recorder.recording and "No audio from iPhone" in caplog.text
