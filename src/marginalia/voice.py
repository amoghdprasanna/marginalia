"""Optional voice input: record the microphone, decide when the speaker is done, transcribe locally.

Hardware and the speech model sit behind small factories so the logic here is testable
without a microphone or a model download.
"""
from __future__ import annotations

import importlib.util
import logging
import threading
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

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

    The floor is the *quietest* calibration block, and never above `max_floor`: if you start
    talking at once, your speech must not become the "room", or the bar ends up above your own
    voice and listening never ends.
    """

    silence_s: float = 1.4
    max_s: float = 30.0
    calibrate_s: float = 0.35
    ratio: float = 3.0
    min_level: float = 0.012
    max_floor: float = 0.008  # a loud room; normal speech is several times this

    max_threshold = 3.0 * 0.008

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._floor: list[float] = []
        self.heard_speech = False
        self._quiet_since: float | None = None

    @property
    def threshold(self) -> float:
        floor = min(min(self._floor), self.max_floor) if self._floor else 0.0
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


def _input_device_name() -> str:
    try:
        import sounddevice as sd

        return str(sd.query_devices(kind="input")["name"])
    except Exception:  # noqa: BLE001
        return "the microphone"


class Recorder:
    """Collects 16 kHz mono audio; `level` is the RMS of the latest block, for the UI.

    `blocks` counts audio blocks received, so the UI can tell "silent" from "no audio at all"
    (a Bluetooth or iPhone mic still switching modes delivers nothing, or exact zeros).
    """

    def __init__(self, stream_factory=_sounddevice_stream, device_name=_input_device_name, stop_timeout=1.5) -> None:
        self._stream_factory = stream_factory
        self._device_name = device_name
        self._stop_timeout = stop_timeout
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self.level = 0.0
        self.blocks = 0
        self.device = ""

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def _on_audio(self, indata, _frames, _time, _status) -> None:
        # Runs on the audio thread. list.append and a float store are atomic under the GIL.
        mono = indata[:, 0].copy()
        self._chunks.append(mono)
        self.level = float(np.sqrt(np.mean(mono * mono)))
        self.blocks += 1

    def start(self) -> None:
        self.stop()
        self._chunks = []
        self.level = 0.0
        self.blocks = 0
        self.device = self._device_name()
        self._stream = self._stream_factory(self._on_audio)
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Stop and return the audio. Never blocks the caller for more than `stop_timeout`:
        PortAudio can hang stopping a device that vanished mid-recording (AirPods switching)."""
        if self._stream is not None:
            stream, self._stream = self._stream, None

            def shut() -> None:
                try:
                    (stream.abort if hasattr(stream, "abort") else stream.stop)()  # abort: don't drain buffers
                    stream.close()
                except Exception as exc:  # noqa: BLE001
                    log.debug("Closing the microphone stream: %s", exc)

            t = threading.Thread(target=shut, name="mic-stop", daemon=True)
            t.start()
            t.join(self._stop_timeout)
            if t.is_alive():
                log.warning("The microphone (%s) did not stop in time; carrying on without it", self.device)
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
