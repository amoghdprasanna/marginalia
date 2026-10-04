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
