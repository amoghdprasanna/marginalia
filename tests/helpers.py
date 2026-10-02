"""Test doubles. Fakes (small working stand-ins) rather than mocks, so tests read as behaviour."""

from __future__ import annotations

from concurrent.futures import Executor, Future
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
from PIL import Image

from marginalia.brain import Answer, Point
from marginalia.capture import Snapshot


def make_snapshot(logical=(1440, 900), dpr=2.0, cursor=(700, 450), origin=(0, 0), color=(250, 250, 250)) -> Snapshot:
    """A blank screen of `logical` size at `dpr`, e.g. a 2x Retina laptop by default."""
    img = Image.new("RGB", (round(logical[0] * dpr), round(logical[1] * dpr)), color)
    return Snapshot(img, (*origin, *logical), cursor)


class ImmediateExecutor(Executor):
    """Runs work inline, so a test sees results without threads or waiting."""

    def submit(self, fn, /, *args, **kwargs):
        fut: Future = Future()
        try:
            fut.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001
            fut.set_exception(exc)
        return fut


class ManualExecutor(Executor):
    """Queues work until the test calls run(); lets a test reorder or interleave requests."""

    def __init__(self) -> None:
        self.queue: list[tuple[Future, object, tuple, dict]] = []

    def submit(self, fn, /, *args, **kwargs):
        fut: Future = Future()
        self.queue.append((fut, fn, args, kwargs))
        return fut

    def run(self, index: int = 0) -> None:
        fut, fn, args, kwargs = self.queue.pop(index)
        try:
            fut.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001
            fut.set_exception(exc)

    def run_all(self) -> None:
        while self.queue:
            self.run()


@dataclass
class FakeBrain:
    """Answers every question with a fixed reply (or raises) and records what it was asked."""

    text: str = "It is the code distance."
    points: list[Point] = field(default_factory=list)
    error: Exception | None = None
    asked: list[tuple[str, list]] = field(default_factory=list)

    def ask(self, prep, lines, question, history) -> Answer:
        self.asked.append((question, list(history)))
        if self.error is not None:
            raise self.error
        return Answer(self.text, list(self.points), "fake-model", 0.1, "")


class FakeStream:
    """Stands in for sounddevice.InputStream; push() plays audio into the callback."""

    def __init__(self, callback) -> None:
        self.callback = callback
        self.started = self.stopped = self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def push(self, samples: np.ndarray) -> None:
        self.callback(samples.reshape(-1, 1).astype(np.float32), len(samples), None, None)


class FakeWhisper:
    """Mimics faster_whisper.WhisperModel.transcribe: returns (segments, info)."""

    def __init__(self, text: str = "what does this mean") -> None:
        self.text = text
        self.calls: list[dict] = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        return [SimpleNamespace(text=f" {self.text} ")], None


class FakeMessages:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response, self.error = response, error
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def fake_client(text: str = '{"answer": "hi", "points": []}', stop_reason: str = "end_turn", error=None, blocks=None):
    """An object shaped like anthropic.Anthropic() for the one call ClaudeBrain makes."""
    content = blocks if blocks is not None else [SimpleNamespace(type="text", text=text)]
    response = SimpleNamespace(content=content, stop_reason=stop_reason, model="claude-opus-5")
    messages = FakeMessages(response, error)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages
