"""Optional voice input: record the microphone, then transcribe locally with faster-whisper."""
from __future__ import annotations

import importlib.util
import threading

import numpy as np

RATE = 16000


def _missing() -> str | None:
    if importlib.util.find_spec("faster_whisper") is None:  # found, not imported: it is slow to load
        return "faster-whisper is not installed. pip install -r requirements-voice.txt"
    try:
        import sounddevice  # noqa: F401
    except Exception as exc:  # noqa: BLE001  (sounddevice raises OSError when PortAudio is missing)
        return f"{exc}. pip install -r requirements-voice.txt"
    return None


class Recorder:
    """Collects 16 kHz mono audio; `level` is the RMS of the latest block, for the UI."""

    def __init__(self) -> None:
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self.level = 0.0

    def start(self) -> None:
        import sounddevice as sd

        self._chunks = []
        self.level = 0.0

        def on_audio(indata, _frames, _time, _status) -> None:
            mono = indata[:, 0].copy()
            self._chunks.append(mono)
            self.level = float(np.sqrt(np.mean(mono * mono)))

        self._stream = sd.InputStream(samplerate=RATE, channels=1, dtype="float32", callback=on_audio)
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)


class Transcriber:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.problem = _missing()
        self.available = self.problem is None
        self._model = None
        self._lock = threading.Lock()

    def warm(self) -> None:
        """Load (and on first run, download) the model so the first question is not slow."""
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size < RATE // 4:
            return ""
        self.warm()
        lang = "en" if self.model_name.endswith(".en") else None
        segments, _ = self._model.transcribe(audio, language=lang, beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
