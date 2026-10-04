"""Wires everything together: hotkey and orb, capture, OCR, the model, and the overlay."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, QPoint, QRect, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

from .brain import BrainError, Cancelled, ClaudeBrain, DemoBrain
from .capture import Snapshot, grab_screen, prepare
from .config import Config, load_config
from .cursor import RestTracker
from .doubtlog import DoubtLog
from .ocr import OCR
from .pointing import place_box, resolve_points
from .ui import AnswerBubble, AskBox, ListenBox, ModeChooser, Orb, PointerOverlay
from .voice import Recorder, Transcriber

HISTORY_TURNS = 4
HIDE_DELAY_MS = 140  # let our own windows disappear before the screenshot
PARTIAL_MS = 50  # redraw a streaming answer at most this often


class Bus(QObject):
    """Signals emitted from worker threads and delivered on the Qt main thread."""

    hotkey = Signal()
    answer_ready = Signal(object)
    answer_partial = Signal(object)
    transcript_ready = Signal(object)


def pretty_hotkey(combo: str) -> str:
    return "+".join(part.strip("<>").capitalize() for part in combo.split("+"))


def start_hotkey(combo: str, callback):
    if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        print("[marginalia] Wayland session: global hotkeys are blocked here. Use the orb, or log in with X11.")
        return None
    try:
        from pynput import keyboard

        listener = keyboard.GlobalHotKeys({combo: callback})
        listener.daemon = True
        listener.start()
        return listener
    except Exception as exc:  # noqa: BLE001
        print(f"[marginalia] Hotkey unavailable ({exc}). Use the orb instead.")
        return None


@dataclass
class Services:
    """Everything the controller talks to that is slow, external or hardware. Tests swap these out."""

    brain: Any
    log: DoubtLog
    ocr: OCR | None = None
    transcriber: Transcriber | None = None
    recorder: Recorder = field(default_factory=Recorder)
    grab: Callable[[int, int], Snapshot] = grab_screen
    pool: Executor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=3))


def default_services(cfg: Config) -> Services:
    return Services(
        brain=DemoBrain() if cfg.demo else ClaudeBrain(cfg),
        log=DoubtLog(cfg.log_dir),
        ocr=OCR() if cfg.ocr_enabled else None,
        transcriber=Transcriber(cfg.whisper_model) if cfg.voice_enabled else None,
    )


class Controller(QObject):
    def __init__(self, cfg: Config, services: Services | None = None) -> None:
        super().__init__()
        self.cfg = cfg
        self.bus = Bus()
        sv = services or default_services(cfg)
        self.brain, self.ocr, self.log, self.pool = sv.brain, sv.ocr, sv.log, sv.pool
        self.transcriber, self.recorder, self.grab = sv.transcriber, sv.recorder, sv.grab

        self.orb = Orb(pretty_hotkey(cfg.hotkey) if cfg.hotkey_enabled else None)
        self.askbox = AskBox()
        self.bubble = AnswerBubble()
        self.overlay = PointerOverlay()
        self.chooser = ModeChooser()
        self.listenbox = ListenBox()
        if self.transcriber is None:
            self.chooser.set_voice_available(False, "disabled in settings")
        elif not self.transcriber.available:
            self.chooser.set_voice_available(False, self.transcriber.problem)
        voice_ok = self.transcriber is not None and self.transcriber.available
        self.askbox.set_voice_available(voice_ok)
        self.bubble.set_voice_available(voice_ok)
        self.listen_id = 0
        self._panels = (self.orb, self.askbox, self.bubble, self.chooser, self.listenbox)

        self.snapshot: Snapshot | None = None
        self.ocr_future = None
        self.history: list[tuple[str, str]] = []
        self.request_id = 0
        self._capturing = False
        # Streamed text arrives faster than it is worth redrawing; keep the newest, draw on a timer.
        self._partial: tuple[int, str, str] | None = None
        self._partial_timer = QTimer(self)
        self._partial_timer.setSingleShot(True)
        self._partial_timer.setInterval(PARTIAL_MS)
        self._partial_timer.timeout.connect(self._draw_partial)

        # Where the mouse last rested on content (not on our windows): the orb asks about that spot.
        start = QCursor.pos()
        self.rest = RestTracker((start.x(), start.y()), time.monotonic())
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._track_cursor)

        self.orb.clicked.connect(self._choose_mode)
        self.orb.type_requested.connect(lambda: self.start_ask(at_cursor=False))
        self.orb.voice_requested.connect(lambda: self.start_voice(at_cursor=False))
        self.chooser.chosen.connect(
            lambda mode: self.start_voice(at_cursor=False) if mode == "voice" else self.start_ask(at_cursor=False)
        )
        self.askbox.voice_requested.connect(self._askbox_to_voice)
        self.bubble.voice_followup.connect(lambda: self.start_voice(at_cursor=False))
        self.listenbox.stop_requested.connect(self._finish_listening)
        self.listenbox.cancelled.connect(self._cancel_listening)
        self.bus.transcript_ready.connect(self._on_transcript)
        self.orb.quit_requested.connect(QApplication.quit)
        self.bus.hotkey.connect(lambda: self.start_ask(at_cursor=True))
        self.bus.answer_ready.connect(self._on_answer)
        self.bus.answer_partial.connect(self._on_partial)
        self.askbox.submitted.connect(self.ask)
        self.bubble.closed.connect(self._end_thread)
        self.bubble.followup.connect(self._followup)
        self.hotkey = None

    def start(self) -> None:
        self.orb.show()
        self._poll.start()
        if self.cfg.hotkey_enabled:
            self.hotkey = start_hotkey(self.cfg.hotkey, self.bus.hotkey.emit)
        mode = "demo mode" if self.cfg.demo else self.cfg.model
        ocr = "on" if self.ocr and self.ocr.available else "off"
        voice = "on" if self.transcriber and self.transcriber.available else "off"
        keys = pretty_hotkey(self.cfg.hotkey) if self.hotkey else "orb only"
        print(f"[marginalia] Ready ({mode}, OCR {ocr}, voice {voice}, trigger: {keys}). Journal: {self.log.dir}")
        if self.transcriber is not None and not self.transcriber.available:
            print(f"[marginalia] Voice not installed ({self.transcriber.problem})")
        elif self.transcriber is not None:
            self.pool.submit(self._warm_voice)
        if self.ocr is not None and not self.ocr.available:
            print("[marginalia] OCR not installed; pointing still works. pip install -e '.[ocr]'")

    def _warm_voice(self) -> None:
        try:
            self.transcriber.warm()
        except Exception as exc:  # noqa: BLE001
            print(f"[marginalia] Could not load the speech model '{self.cfg.whisper_model}': {exc}")

    # cursor tracking -------------------------------------------------------------------------

    def _on_own_window(self, pos: QPoint) -> bool:
        return any(w.isVisible() and w.frameGeometry().contains(pos) for w in self._panels)

    def _track_cursor(self) -> None:
        pos = QCursor.pos()
        if not self._on_own_window(pos):
            self.rest.feed(time.monotonic(), (pos.x(), pos.y()))

    @property
    def last_rest(self) -> QPoint:
        return QPoint(*self.rest.rest)

    # capture ---------------------------------------------------------------------------------

    def _choose_mode(self) -> None:
        if self.chooser.isVisible():
            self.chooser.hide()
            return
        self.chooser.open_beside(self.orb.frameGeometry(), self.orb.screen().availableGeometry())

    def start_ask(self, at_cursor: bool) -> None:
        pos = QCursor.pos() if at_cursor else self.last_rest
        self._capture(pos, then=lambda: self.askbox.open_at(pos, QRect(*self.snapshot.screen_geo)))

    def _capture(self, pos: QPoint, then) -> None:
        if self._capturing:
            return
        self._capturing = True
        self.request_id += 1  # anything still in flight is now stale
        self._stop_recorder()
        for w in (self.overlay, self.askbox, self.bubble, self.chooser, self.listenbox, self.orb):
            w.hide()
        QTimer.singleShot(HIDE_DELAY_MS, self, lambda: self._finish_capture(pos, then))

    def _finish_capture(self, pos: QPoint, then) -> None:
        try:
            self.snapshot = self.grab(pos.x(), pos.y())
        except Exception as exc:  # noqa: BLE001
            self.orb.show()
            self._capturing = False
            self.bubble.show_error("Screen capture", str(exc))
            self._show_bubble_near(pos, [])
            return
        self.orb.show()
        self._capturing = False
        self.ocr_future = None
        if self.ocr is not None and self.ocr.available:  # runs while you type the question
            self.ocr_future = self.pool.submit(self.ocr.read, self.snapshot.image)
        then()

    # voice ------------------------------------------------------------------------------------

    def start_voice(self, at_cursor: bool) -> None:
        if self.transcriber is None or not self.transcriber.available:
            return self.start_ask(at_cursor)
        pos = QCursor.pos() if at_cursor else self.last_rest
        self._capture(pos, then=lambda: self._begin_listening(pos))

    def _askbox_to_voice(self) -> None:
        if self.snapshot is not None:  # the screen was already grabbed for this question
            self._begin_listening(QPoint(*self.snapshot.cursor))

    def _begin_listening(self, pos: QPoint) -> None:
        self.listen_id += 1
        screen = QRect(*self.snapshot.screen_geo)
        try:
            self.recorder.start()
        except Exception as exc:  # noqa: BLE001
            self.listenbox.open_at(pos, screen, lambda: 0.0)
            self.listenbox.show_problem(f"Microphone unavailable: {exc}"[:90])
            return
        self.listenbox.open_at(pos, screen, lambda: self.recorder.level)

    def _stop_recorder(self):
        try:
            return self.recorder.stop()
        except Exception:  # noqa: BLE001
            return None

    def _finish_listening(self) -> None:
        audio = self._stop_recorder()
        if audio is None:
            return self.listenbox.show_problem("Recording failed. Try again.")
        self.listenbox.show_transcribing()
        lid = self.listen_id
        future = self.pool.submit(self.transcriber.transcribe, audio)
        future.add_done_callback(lambda f: self.bus.transcript_ready.emit((lid, f)))

    def _cancel_listening(self) -> None:
        self.listen_id += 1
        self._stop_recorder()

    def _on_transcript(self, payload) -> None:
        lid, future = payload
        if lid != self.listen_id or not self.listenbox.isVisible():
            return
        try:
            text = future.result()
        except Exception as exc:  # noqa: BLE001
            return self.listenbox.show_problem(f"Transcription failed: {exc}"[:90])
        if not text:
            return self.listenbox.show_problem("Didn't catch that.")
        self.listenbox.close_quietly()
        self.ask(text)

    # asking ----------------------------------------------------------------------------------

    def ask(self, question: str) -> None:
        snap, ocr_future = self.snapshot, self.ocr_future
        if snap is None:
            return
        self.request_id += 1
        rid = self.request_id
        history = list(self.history)
        cursor = QPoint(*snap.cursor)
        self.overlay.clear()
        self.bubble.show_thinking(question)
        self._show_bubble_near(cursor, [])
        self.orb.set_busy(True)

        def on_text(text: str) -> None:  # worker thread
            if rid != self.request_id:
                raise Cancelled  # nobody is waiting: stop paying for tokens
            self.bus.answer_partial.emit((rid, question, text))

        def work():
            lines = []
            if ocr_future is not None:
                try:
                    lines = ocr_future.result(timeout=10)
                except Exception:  # noqa: BLE001
                    lines = []
            prep = prepare(snap, hires=self.cfg.hires)
            answer = self.brain.ask(prep, lines, question, history, on_text=on_text)
            return prep, lines, answer

        future = self.pool.submit(work)
        future.add_done_callback(lambda f: self.bus.answer_ready.emit((rid, question, snap, f)))

    def _on_partial(self, payload) -> None:
        if payload[0] != self.request_id:
            return
        self._partial = payload
        if not self._partial_timer.isActive():
            self._partial_timer.start()

    def _draw_partial(self) -> None:
        if self._partial is None or self._partial[0] != self.request_id:
            return
        _, question, text = self._partial
        self.bubble.show_partial(question, text)
        self._keep_bubble_on_screen()

    def _drop_partial(self) -> None:
        self._partial_timer.stop()
        self._partial = None

    def _on_answer(self, payload) -> None:
        rid, question, snap, future = payload
        if rid != self.request_id:
            return
        self._drop_partial()  # a redraw still queued must not paint over the final answer
        self.orb.set_busy(False)
        cursor = QPoint(*snap.cursor)
        try:
            prep, lines, answer = future.result()
        except BrainError as exc:
            self.bubble.show_error(question, str(exc))
            self._show_bubble_near(cursor, [])
            return
        except Exception as exc:  # noqa: BLE001
            self.bubble.show_error(question, f"Something went wrong: {exc!r}")
            self._show_bubble_near(cursor, [])
            return

        targets = resolve_points(prep, snap, lines, answer.points)
        self.overlay.point_to(QRect(*snap.screen_geo), cursor, targets)
        meta = f"{answer.model}, {answer.elapsed:.1f}s"
        if answer.first_text is not None:
            meta = f"{answer.model}, first words {answer.first_text:.1f}s, done {answer.elapsed:.1f}s"
        if lines:
            meta += f", {len(lines)} OCR lines"
        self.bubble.show_answer(question, answer.text, meta)
        keep_clear = []
        for x, y, _ in targets:  # the ring and the label that floats above-right of it
            keep_clear += [QPoint(int(x), int(y)), QPoint(int(x) + 90, int(y) - 34), QPoint(int(x) + 180, int(y) - 34)]
        self._show_bubble_near(cursor, keep_clear)

        self.history = (self.history + [(question, answer.text)])[-HISTORY_TURNS:]
        try:
            self.log.add(question, answer.text, prep.full, answer.model)
        except OSError as exc:
            print(f"[marginalia] Could not write the journal: {exc}")

    def _followup(self, question: str) -> None:
        # Re-capture first: the lecture or page may have moved on since the last question.
        pos = self.last_rest
        self._capture(pos, then=lambda: self.ask(question))

    def _end_thread(self) -> None:
        self.request_id += 1
        self._drop_partial()
        self.history.clear()
        self.overlay.clear()
        self.orb.set_busy(False)

    def _keep_bubble_on_screen(self) -> None:
        """A streaming bubble grows downwards; slide it up rather than let it run off the screen."""
        screen = QRect(*self.snapshot.screen_geo) if self.snapshot else self.orb.screen().geometry()
        g = self.bubble.frameGeometry()
        if g.bottom() > screen.bottom() - 12:
            self.bubble.move(g.x(), max(screen.top() + 12, screen.bottom() - 12 - g.height()))

    def _show_bubble_near(self, cursor: QPoint, targets: list[QPoint]) -> None:
        screen = QRect(*self.snapshot.screen_geo) if self.snapshot else self.orb.screen().geometry()
        self.bubble.adjustSize()
        x, y = place_box(
            (self.bubble.width(), self.bubble.height()),
            (screen.x(), screen.y(), screen.width(), screen.height()),
            (cursor.x(), cursor.y()),
            [(t.x(), t.y()) for t in targets] + [(self.orb.geometry().center().x(), self.orb.geometry().center().y())],
        )
        self.bubble.move(x, y)
        self.bubble.show()
        self.bubble.raise_()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="marginalia", description="Screen-aware study companion.")
    ap.add_argument("--demo", action="store_true", help="canned answers, no API key needed")
    ap.add_argument("--no-hotkey", action="store_true", help="disable the global shortcut (use the orb)")
    ap.add_argument("--no-ocr", action="store_true", help="skip OCR even if it is installed")
    ap.add_argument("--no-voice", action="store_true", help="disable asking by voice")
    args = ap.parse_args(argv)

    cfg = load_config(demo=args.demo, no_hotkey=args.no_hotkey, no_ocr=args.no_ocr, no_voice=args.no_voice)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Marginalia")
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C in the terminal quits

    if not cfg.demo and not cfg.api_key:
        print("[marginalia] No ANTHROPIC_API_KEY found. Add it to .env, or run with --demo.")

    controller = Controller(cfg)
    controller.start()
    sys.exit(app.exec())
