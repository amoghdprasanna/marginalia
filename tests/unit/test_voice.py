"""Voice: when to stop listening, what we record, and how we transcribe, all without hardware."""

import threading

import numpy as np
import pytest
from helpers import FakeStream, FakeWhisper

from marginalia.voice import RATE, Recorder, SilenceDetector, Transcriber


def run(detector, levels, dt=0.05):
    """Feed a level trace; return the time the detector said stop, or None."""
    for i, level in enumerate(levels):
        if detector.feed(i * dt, level):
            return i * dt
    return None


def test_pause_after_speech_ends_the_question():
    d = SilenceDetector(silence_s=1.0)
    trace = [0.002] * 8 + [0.08] * 30 + [0.002] * 40
    stop = run(d, trace)
    assert stop == pytest.approx((8 + 30) * 0.05 + 1.0, abs=0.06)


def test_silence_before_speaking_does_not_end_it():
    assert run(SilenceDetector(silence_s=1.0, max_s=100), [0.002] * 200) is None


def test_short_breath_mid_sentence_does_not_end_it():
    d = SilenceDetector(silence_s=1.0)
    trace = [0.002] * 8 + [0.08] * 10 + [0.002] * 10 + [0.08] * 10  # 0.5 s gap
    assert run(d, trace) is None


def test_noisy_room_raises_the_threshold():
    d = SilenceDetector()
    run(d, [0.02] * 8)  # calibration in a noisy room
    assert d.threshold == pytest.approx(0.06)
    assert not d.feed(1.0, 0.04)  # the room noise is not speech
    assert not d.heard_speech


def test_hard_limit():
    assert SilenceDetector(max_s=2.0).feed(2.0, 0.5)


def test_reset_starts_fresh():
    d = SilenceDetector(silence_s=0.2)
    run(d, [0.0] * 8 + [0.1] * 4)
    d.reset()
    assert not d.heard_speech and d.threshold == d.min_level


def test_recorder_collects_audio_and_level():
    streams = []
    r = Recorder(stream_factory=lambda cb: streams.append(FakeStream(cb)) or streams[-1])
    r.start()
    assert r.recording and streams[0].started
    streams[0].push(np.full(1600, 0.5))
    streams[0].push(np.full(1600, 0.1))
    assert r.level == pytest.approx(0.1)
    audio = r.stop()
    assert audio.shape == (3200,) and not r.recording
    assert streams[0].stopped and streams[0].closed


def test_recorder_restart_drops_old_audio_and_closes_old_stream():
    streams = []
    r = Recorder(stream_factory=lambda cb: streams.append(FakeStream(cb)) or streams[-1])
    r.start()
    streams[0].push(np.ones(100))
    r.start()
    assert streams[0].closed
    assert r.stop().size == 0


def test_stop_without_start_is_harmless():
    assert Recorder(stream_factory=FakeStream).stop().size == 0


def make_transcriber(model=None, name="base.en"):
    model = model or FakeWhisper()
    calls = []
    t = Transcriber(name, model_factory=lambda n: calls.append(n) or model, problem=None)
    return t, model, calls


def test_transcribes_and_trims():
    t, model, _ = make_transcriber(FakeWhisper("what is a stabilizer"))
    assert t.transcribe(np.zeros(RATE)) == "what is a stabilizer"
    assert model.calls[0]["language"] == "en" and model.calls[0]["vad_filter"]


def test_multilingual_model_detects_language():
    t, model, _ = make_transcriber(name="small")
    t.transcribe(np.zeros(RATE))
    assert model.calls[0]["language"] is None


def test_a_click_is_not_a_question():
    t, model, calls = make_transcriber()
    assert t.transcribe(np.zeros(RATE // 10)) == ""
    assert calls == []  # did not even load the model


def test_model_loads_once_even_under_concurrency():
    t, _, calls = make_transcriber()
    threads = [threading.Thread(target=t.warm) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert calls == ["base.en"]


def test_reports_why_voice_is_unavailable():
    t = Transcriber("base.en", problem="no mic library")
    assert not t.available and t.problem == "no mic library"


def test_missing_whisper_package_is_named(monkeypatch):
    import importlib.util

    from marginalia import voice

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert "faster-whisper is not installed" in voice._missing()


def test_missing_portaudio_is_named(monkeypatch):
    import sys

    from marginalia import voice

    monkeypatch.setattr(voice.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setitem(sys.modules, "sounddevice", None)  # import fails, as without PortAudio
    problem = voice._missing()
    assert problem and "pip install -e '.[voice]'" in problem
    assert not Transcriber("tiny.en").available
