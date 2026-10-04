"""Optional voice input: record the microphone, decide when the speaker is done, transcribe locally.

Hardware and the speech model sit behind small factories so the logic here is testable
without a microphone or a model download.
"""
from __future__ import annotations

import importlib.util
import threading
from dataclasses import dataclass

import numpy as np

RATE = 16000


def _missing() -> str | None:
    if importlib.util.find_spec("faster_whisper") is None:  # found, not imported: it is slow to load
        return "faster-whisper is not installed. pip install -e '.[voice]'"
    try:
        import sounddevice  # noqa: F401
    except Exception as exc:  # noqa: BLE001  (sounddevice raises OSError when PortAudio is missing)
        return f"{exc}. pip install -e '.[voice]'"
    return None


@dataclass
class SilenceDetector:
    """Ends a recording on a pause after speech. Pure: feed it (time, level), ask if it is done.

    The first `calibrate_s` seconds measure the room's noise floor; speech is anything louder
    than `ratio` times that floor (and never below `min_level`, so a dead-silent room still works).
    """

    silence_s: float = 1.4
    max_s: float = 45.0
    calibrate_s: float = 0.35
    ratio: float = 3.0
    min_level: float = 0.012

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._floor: list[float] = []
        self.heard_speech = False
        self._quiet_since: float | None = None

    @property
    def threshold(self) -> float:
        floor = sum(self._floor) / len(self._floor) if self._floor else 0.0
        return max(self.ratio * floor, self.min_level)

    def feed(self, t: float, level: float) -> bool:
        """Returns True once the question is over."""
        if t >= self.max_s:
            return True
        if t < self.calibrate_s:
            self._floor.append(level)
            return False
        if level > self.threshold:
            self.heard_speech, self._quiet_since = True, None
            return False
        if not self.heard_speech:
            return False
        if self._quiet_since is None:
            self._quiet_since = t
        return t - self._quiet_since >= self.silence_s


def _sounddevice_stream(callback):
    import sounddevice as sd

    return sd.InputStream(samplerate=RATE, channels=1, dtype="float32", callback=callback)


class Recorder:
    """Collects 16 kHz mono audio; `level` is the RMS of the latest block, for the UI."""

    def __init__(self, stream_factory=_sounddevice_stream) -> None:
        self._stream_factory = stream_factory
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self.level = 0.0

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def _on_audio(self, indata, _frames, _time, _status) -> None:
        # Runs on the audio thread. list.append and a float store are atomic under the GIL.
        mono = indata[:, 0].copy()
        self._chunks.append(mono)
        self.level = float(np.sqrt(np.mean(mono * mono)))

    def start(self) -> None:
        self.stop()
        self._chunks = []
        self.level = 0.0
        self._stream = self._stream_factory(self._on_audio)
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            stream, self._stream = self._stream, None
            stream.stop()
            stream.close()
        return np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)


def _whisper_model(name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(name, device="cpu", compute_type="int8")


class Transcriber:
    MIN_SAMPLES = RATE // 4  # under 0.25 s is a click, not a question

    def __init__(self, model_name: str, model_factory=_whisper_model, problem: str | None = "check") -> None:
        self.model_name = model_name
        self._factory = model_factory
        self.problem = _missing() if problem == "check" else problem
        self.available = self.problem is None
        self._model = None
        self._lock = threading.Lock()

    def warm(self) -> None:
        """Load (and on first run, download) the model so the first question is not slow."""
        with self._lock:
            if self._model is None:
                self._model = self._factory(self.model_name)

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size < self.MIN_SAMPLES:
            return ""
        self.warm()
        lang = "en" if self.model_name.endswith(".en") else None
        segments, _ = self._model.transcribe(audio, language=lang, beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
