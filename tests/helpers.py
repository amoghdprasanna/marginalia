"""Test doubles. Fakes (small working stand-ins) rather than mocks, so tests read as behaviour."""

from __future__ import annotations

import json
from concurrent.futures import Executor, Future
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
from PIL import Image

from marginalia.app import Controller, Services
from marginalia.brain import Answer, Point
from marginalia.capture import Snapshot
from marginalia.doubtlog import DoubtLog
from marginalia.voice import Recorder, Transcriber


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
    partials: list[str] = field(default_factory=list)  # streamed to on_text before answering
    asked: list[tuple[str, list]] = field(default_factory=list)
    delivered: list[str] = field(default_factory=list)  # partials the caller accepted (didn't cancel)
    lines_seen: list[list] = field(default_factory=list)  # OCR lines handed in with each question

    def ask(self, prep, lines, question, history, on_text=None) -> Answer:
        self.asked.append((question, list(history)))
        self.lines_seen.append(list(lines))
        for t in self.partials:
            if on_text is not None:
                on_text(t)
                self.delivered.append(t)
        if self.error is not None:
            raise self.error
        return Answer(self.text, list(self.points), "fake-model", 0.1, "")


class FakeOCR:
    """Returns fixed text lines (or raises), like ocr.OCR with an engine installed."""

    def __init__(self, lines=(), available: bool = True, error: Exception | None = None) -> None:
        self.lines, self.available, self.error = list(lines), available, error
        self.reads = 0

    def read(self, image):
        self.reads += 1
        if self.error is not None:
            raise self.error
        return list(self.lines)


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


class FakeMessageStream:
    """What `client.beta.messages.stream(...)` returns: a context manager with text_stream."""

    def __init__(self, response, chunks: list[str], error: Exception | None) -> None:
        self.response, self.chunks, self.error = response, chunks, error
        self.closed = False
        self.read = 0  # chunks the caller actually consumed
        self.mid_error: Exception | None = None  # raised after the first chunk, like an SSE error event

    def __enter__(self):
        if self.error is not None:  # the SDK sends the request on entry
            raise self.error
        return self

    def __exit__(self, *exc) -> None:
        self.closed = True

    @property
    def text_stream(self):
        for c in self.chunks:
            self.read += 1
            yield c
            if self.mid_error is not None:
                raise self.mid_error

    def get_final_message(self):
        return self.response


class FakeMessages:
    def __init__(self, response=None, error: Exception | None = None, chunk: int = 7) -> None:
        self.response, self.error, self.chunk = response, error, chunk
        self.mid_error: Exception | None = None
        self.requests: list[dict] = []
        self.streams: list[FakeMessageStream] = []

    def stream(self, **kwargs):
        self.requests.append(kwargs)
        text = "".join(getattr(b, "text", "") for b in self.response.content if getattr(b, "type", "") == "text")
        chunks = [text[i : i + self.chunk] for i in range(0, len(text), self.chunk)]
        s = FakeMessageStream(self.response, chunks, self.error)
        s.mid_error = self.mid_error
        self.streams.append(s)
        return s


def fake_client(text: str = '{"answer": "hi", "points": []}', stop_reason: str = "end_turn", error=None, blocks=None):
    """An object shaped like anthropic.Anthropic() for the one call ClaudeBrain makes.

    The reply streams back in 7-character chunks, cutting through words and escapes on purpose.
    """
    content = blocks if blocks is not None else [SimpleNamespace(type="text", text=text)]
    response = SimpleNamespace(content=content, stop_reason=stop_reason, model="claude-opus-5-5", usage=None)
    messages = FakeMessages(response, error)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


class FakeKeyring:
    """In-memory stand-in for the keyring module (get/set/delete_password)."""

    def __init__(self, error: Exception | None = None) -> None:
        self.data: dict[tuple[str, str], str] = {}
        self.error = error

    def get_password(self, service, account):
        if self.error is not None:
            raise self.error
        return self.data.get((service, account))

    def set_password(self, service, account, value):
        if self.error is not None:
            raise self.error
        self.data[(service, account)] = value

    def delete_password(self, service, account):
        if self.error is not None or (service, account) not in self.data:
            raise self.error or KeyError(account)
        del self.data[(service, account)]


# controller harness ---------------------------------------------------------------------


def build(qtbot, cfg, *, brain=None, pool=None, voice_text=None, grab=None, ocr=None, log=None):
    streams = []
    services = Services(
        brain=brain or FakeBrain(),
        log=log or DoubtLog(cfg.log_dir),
        ocr=ocr,
        transcriber=None
        if voice_text is None
        else Transcriber("tiny.en", model_factory=lambda n: FakeWhisper(voice_text), problem=None),
        recorder=Recorder(stream_factory=lambda cb: streams.append(FakeStream(cb)) or streams[-1]),
        grab=grab or (lambda x, y: make_snapshot(cursor=(x, y))),
        pool=pool or ImmediateExecutor(),
    )
    c = Controller(cfg, services)
    for w in (c.orb, c.askbox, c.bubble, c.overlay, c.chooser, c.listenbox):
        qtbot.addWidget(w)
    c.streams = streams
    return c


def ask_typed(qtbot, c, question):
    c.start_ask(at_cursor=False)
    qtbot.waitUntil(c.askbox.isVisible)
    c.askbox.edit.setText(question)
    c.askbox._submit()


# reply envelopes --------------------------------------------------------------------------


def envelope(answer: str = "ok", points=()) -> str:
    """A reply as the API returns it under ANSWER_SCHEMA."""
    return json.dumps({"answer": answer, "points": list(points)})


def point_dict(**kw) -> dict:
    return {"image": "full", "x": 10, "y": 20, "line": None, "label": "eq 4", **kw}
