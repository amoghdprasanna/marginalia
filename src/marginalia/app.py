"""Wires everything together: hotkey and orb, capture, OCR, the model, and the overlay."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, QPoint, QProcess, QRect, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication

from . import __version__
from .brain import BrainError, Cancelled, ClaudeBrain, DemoBrain
from .capture import Snapshot, default_grab, prepare
from .config import Config, SettingsStore, load_config, settings_path
from .crash import CrashReporter, issue_url
from .cursor import RestTracker
from .doubtlog import DoubtLog
from .hotkeys import format_combo, start_hotkeys
from .journal import Journal
from .logs import setup_logging
from .ocr import OCR
from .permissions import Fixer, default_probes, host_app, needs_attention, run_checks
from .pointing import place_box, resolve_points
from .secrets import Keychain
from .ui import (
    AnswerBubble,
    AskBox,
    JournalWindow,
    ListenBox,
    ModeChooser,
    Notice,
    Orb,
    PointerOverlay,
    SettingsWindow,
    SetupWindow,
)
from .ui.paint import app_icon
from .updates import Release, due, fetch_latest, is_newer
from .voice import Recorder, Transcriber

log = logging.getLogger(__name__)

HISTORY_TURNS = 4
# Enough for OCR, the answer, transcription and a speech-model download at once, plus answers that
# went stale while the model was still thinking (they stop at their first words, not before).
WORKERS = 6
HIDE_DELAY_MS = 140  # let our own windows disappear before the screenshot
PARTIAL_MS = 50  # redraw a streaming answer at most this often
TAP_S = 0.35  # a voice-key press shorter than this is a tap: listen until a pause instead of until release


class Bus(QObject):
    """Signals emitted from worker threads and delivered on the Qt main thread."""

    hotkey = Signal()
    voice_down = Signal()  # the hold-to-talk key went down...
    voice_up = Signal()  # ...and came back up
    answer_ready = Signal(object)
    answer_partial = Signal(object)
    transcript_ready = Signal(object)
    update_ready = Signal(object)
    journal_partial = Signal(object)
    journal_ready = Signal(object)


def make_brain(cfg: Config):
    return DemoBrain() if cfg.demo else ClaudeBrain(cfg)


def make_ocr(cfg: Config) -> OCR | None:
    return OCR() if cfg.ocr_enabled else None


def make_transcriber(cfg: Config) -> Transcriber | None:
    return Transcriber(cfg.whisper_model) if cfg.voice_enabled else None


@dataclass
class Factories:
    """How to build the services a settings change can replace. Tests pass fakes."""

    brain: Callable[[Config], Any] = make_brain
    ocr: Callable[[Config], OCR | None] = make_ocr
    transcriber: Callable[[Config], Transcriber | None] = make_transcriber


@dataclass
class Services:
    """Everything the controller talks to that is slow, external or hardware. Tests swap these out."""

    brain: Any
    log: DoubtLog
    ocr: OCR | None = None
    transcriber: Transcriber | None = None
    recorder: Recorder = field(default_factory=Recorder)
    grab: Callable[[int, int], Snapshot] = field(default_factory=default_grab)
    pool: Executor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=WORKERS))
    store: SettingsStore = field(default_factory=SettingsStore)
    keychain: Keychain = field(default_factory=Keychain)
    factories: Factories = field(default_factory=Factories)
    probes: Any = field(default_factory=default_probes)
    # App bookkeeping (when updates were last checked...), kept apart from your settings.
    state: SettingsStore = field(default_factory=lambda: SettingsStore(settings_path().with_name("state.json")))
    fetch_release: Callable[[], Release | None] = fetch_latest


def default_services(cfg: Config) -> Services:
    return Services(
        brain=make_brain(cfg), log=DoubtLog(cfg.log_dir), ocr=make_ocr(cfg), transcriber=make_transcriber(cfg)
    )


# Settings that, when changed, need a new brain (the others are read per question or elsewhere).
BRAIN_KEYS = {"model", "effort", "api_key", "user_context", "max_tokens", "hires", "demo"}
HOTKEY_KEYS = {"hotkey", "voice_hotkey", "hotkey_enabled"}


class Controller(QObject):
    def __init__(self, cfg: Config, services: Services | None = None) -> None:
        super().__init__()
        self.cfg = cfg
        self.bus = Bus()
        sv = services or default_services(cfg)
        self.brain, self.ocr, self.log, self.pool = sv.brain, sv.ocr, sv.log, sv.pool
        self.transcriber, self.recorder, self.grab = sv.transcriber, sv.recorder, sv.grab
        self.store, self.keychain, self.factories, self.probes = sv.store, sv.keychain, sv.factories, sv.probes
        self.state, self.fetch_release = sv.state, sv.fetch_release
        self.available_update: Release | None = None

        self.orb = Orb(None)
        self.askbox = AskBox()
        self.bubble = AnswerBubble()
        self.overlay = PointerOverlay()
        self.chooser = ModeChooser()
        self.listenbox = ListenBox()
        self.settings_window: SettingsWindow | None = None
        self.setup_window: SetupWindow | None = None
        self.journal_window: JournalWindow | None = None
        self.notice: Notice | None = None  # the latest
        self.notices: list[Notice] = []  # every one still open: Qt doesn't keep a window alive for us
        self.journal_request = 0
        self._show_hotkeys()
        self._show_voice_availability()
        self.listen_id = 0
        self._panels = (self.orb, self.askbox, self.bubble, self.chooser, self.listenbox)

        self.snapshot: Snapshot | None = None
        self.ocr_future = None
        self.history: list[tuple[str, str]] = []
        self.thread_id = ""  # journal id of this thread's first answer; "" until it has one
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
        self.chooser.journal_requested.connect(self.open_journal)
        self.chooser.settings_requested.connect(self.open_settings)
        self.chooser.chosen.connect(
            lambda mode: self.start_voice(at_cursor=False) if mode == "voice" else self.start_ask(at_cursor=False)
        )
        self.askbox.voice_requested.connect(self._askbox_to_voice)
        self.bubble.voice_followup.connect(lambda: self.start_voice(at_cursor=False))
        self.listenbox.stop_requested.connect(self._finish_listening)
        self.listenbox.cancelled.connect(self._cancel_listening)
        # A new question hid the bubble when it captured. Cancelling it leaves nothing on screen,
        # so the thread ends too; otherwise the next question would carry answers you can't see.
        self.askbox.cancelled.connect(self._end_thread)
        self.bus.transcript_ready.connect(self._on_transcript)
        self.orb.quit_requested.connect(QApplication.quit)
        self.orb.settings_requested.connect(self.open_settings)
        self.orb.setup_requested.connect(self.open_setup)
        self.orb.journal_requested.connect(self.open_journal)
        self.orb.update_requested.connect(self.download_update)
        self.orb.check_updates_requested.connect(lambda: self.check_for_updates(force=True))
        self.bus.update_ready.connect(self._on_update_checked)
        self.bus.journal_partial.connect(self._on_journal_partial)
        self.bus.journal_ready.connect(self._on_journal_answer)
        self.bus.hotkey.connect(lambda: self.start_ask(at_cursor=True))
        self.bus.voice_down.connect(self._voice_key_down)
        self.bus.voice_up.connect(self._voice_key_up)
        self._holding = False
        self._hold_t0 = 0.0
        self.bus.answer_ready.connect(self._on_answer)
        self.bus.answer_partial.connect(self._on_partial)
        self.askbox.submitted.connect(self.ask)
        self.bubble.closed.connect(self._end_thread)
        self.bubble.followup.connect(self._followup)
        self.bubble.replay_requested.connect(self.replay_markers)
        self._last_pointing: tuple[QRect, QPoint, list] | None = None
        self.hotkey = None

    def start(self) -> None:
        self.orb.show()
        self._poll.start()
        self._start_hotkeys()
        mode = "demo mode" if self.cfg.demo else self.cfg.model
        ocr = "on" if self.ocr and self.ocr.available else "off"
        voice = "on" if self.transcriber and self.transcriber.available else "off"
        keys = format_combo(self.cfg.hotkey) if self.hotkey else "orb only"
        log.info("Ready (%s, OCR %s, voice %s, trigger: %s). Journal: %s", mode, ocr, voice, keys, self.log.dir)
        if self.transcriber is not None and not self.transcriber.available:
            log.warning("Voice not installed (%s)", self.transcriber.problem)
        elif self.transcriber is not None:
            self.pool.submit(self._warm_voice)
        if self.ocr is not None and not self.ocr.available:
            log.warning("OCR not installed; pointing still works. pip install -e '.[ocr]'")

    def stop(self) -> None:
        """Undo start(): stop polling the cursor, release the hotkey hook and the microphone."""
        self._poll.stop()
        self._drop_partial()
        self.request_id += 1  # an answer still streaming is cancelled at its next chunk
        self._stop_hotkeys()
        self._stop_recorder()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _start_hotkeys(self) -> None:
        self._stop_hotkeys()
        if not self.cfg.hotkey_enabled:
            return
        bindings = [(self.cfg.hotkey, self.bus.hotkey.emit, None)]
        if self.cfg.voice_hotkey:
            bindings.append((self.cfg.voice_hotkey, self.bus.voice_down.emit, self.bus.voice_up.emit))
        self.hotkey = start_hotkeys(bindings)

    def _stop_hotkeys(self) -> None:
        if self.hotkey is not None:
            self.hotkey.stop()
            self.hotkey = None

    def _shortcut_labels(self) -> tuple[str | None, str | None]:
        """The shortcuts as people read them; the voice one only when voice works."""
        on = self.cfg.hotkey_enabled
        ask = format_combo(self.cfg.hotkey) if on and self.cfg.hotkey else None
        voice = format_combo(self.cfg.voice_hotkey) if on and self.cfg.voice_hotkey else None
        voice_ok = self.transcriber is not None and self.transcriber.available
        return ask, voice if voice_ok else None

    def _show_hotkeys(self) -> None:
        on = self.cfg.hotkey_enabled
        self.orb.set_hotkeys(
            format_combo(self.cfg.hotkey) if on and self.cfg.hotkey else None,
            format_combo(self.cfg.voice_hotkey) if on and self.cfg.voice_hotkey else None,
        )
        self.chooser.set_shortcuts(*self._shortcut_labels())

    def _show_voice_availability(self) -> None:
        if self.transcriber is None:
            self.chooser.set_voice_available(False, "turn on voice in Settings")
        elif not self.transcriber.available:
            self.chooser.set_voice_available(False, self.transcriber.problem)
        else:
            self.chooser.set_voice_available(True)
        voice_ok = self.transcriber is not None and self.transcriber.available
        self.askbox.set_voice_available(voice_ok)
        self.bubble.set_voice_available(voice_ok)

    # settings ---------------------------------------------------------------------------------

    def open_settings(self) -> None:
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.cfg, self.store, self.keychain)
            self.settings_window.saved.connect(self.reload_settings)
            self.settings_window.saved.connect(self._refresh_setup)
            self.settings_window.closed.connect(self._start_hotkeys)
        # A registered hotkey is swallowed before the window sees it, so you couldn't record it again.
        self._stop_hotkeys()
        self.settings_window.open(self.cfg)

    def _refresh_setup(self) -> None:
        if self.setup_window is not None and (self.setup_window.isVisible() or self.sender() is self.setup_window):
            self.setup_window.show_checks(self.setup_checks(), host_app(), *self._shortcut_labels())

    # crash reports ----------------------------------------------------------------------------

    @staticmethod
    def open_url(url: QUrl) -> bool:
        return QDesktopServices.openUrl(url)

    def offer_crash_reports(self, reporter: CrashReporter) -> None:
        """If you opted in and the last run hit an error, offer to report it (ADR 0020)."""
        if not self.cfg.crash_reports:
            return
        pending = reporter.pending()
        if not pending:
            return
        _, report = pending[-1]

        def handled() -> None:
            for path, _r in pending:
                reporter.mark_handled(path)

        def send() -> None:
            self.open_url(QUrl(issue_url(report)))
            handled()

        more = f" It happened {len(pending)} times; this is the latest." if len(pending) > 1 else ""
        self._notice(
            "Marginalia hit an error last time",
            f"{report.get('type')}: {report.get('message')}{more}\n\n"
            "Reporting opens a GitHub issue with the error and recent log lines (no questions or answers), "
            "which you can read and edit before sending. Nothing is sent otherwise.",
            [
                ("Show the report", lambda: self.open_url(QUrl.fromLocalFile(str(reporter.dir)))),
                ("Not now", handled),
                ("Report…", send),
            ],
        )

    # updates ----------------------------------------------------------------------------------

    def check_for_updates(self, force: bool = False) -> None:
        """Once a day (or now, from the menu), ask GitHub for the latest release (ADR 0021)."""
        if not force and not (self.cfg.check_updates and due(self.state.load().get("update_checked_at"))):
            return
        future = self.pool.submit(self.fetch_release)
        future.add_done_callback(lambda f: self.bus.update_ready.emit((force, f)))

    def _on_update_checked(self, payload) -> None:
        force, future = payload
        try:
            release = future.result()
        except Exception:  # noqa: BLE001
            release = None
        state = self.state.load()
        try:
            self.state.save({"update_checked_at": datetime.now().isoformat(timespec="seconds")})
        except OSError as exc:
            log.debug("Could not save app state: %s", exc)
        if release is None or not is_newer(release.version):
            if force:
                text = "You have the latest version." if release else "Couldn't reach GitHub to check."
                self._notice(f"Marginalia {__version__}", text, [("OK", None)])
            return
        self.available_update = release
        self.orb.set_update(release.version)
        log.info("Marginalia %s is available (you have %s)", release.version, __version__)
        if force or state.get("update_notified") != release.version:
            try:
                self.state.save({"update_notified": release.version})
            except OSError:
                pass
            notes = release.notes.strip()
            notes = (notes[:400] + "…") if len(notes) > 400 else notes
            self._notice(
                f"Marginalia {release.version} is available",
                f"You have {__version__}.\n\n{notes}".strip(),
                [("Later", None), ("Download…", self.download_update)],
            )

    def download_update(self) -> None:
        if self.available_update is not None:
            self.open_url(QUrl(self.available_update.download_url()))

    def _notice(self, title: str, text: str, buttons) -> None:
        self.notices = [n for n in self.notices if n.isVisible()]
        self.notice = Notice(title, text, buttons)
        self.notices.append(self.notice)
        self.notice.open()

    # journal ----------------------------------------------------------------------------------

    def open_journal(self) -> None:
        if self.journal_window is None:
            self.journal_window = JournalWindow(Journal(self.cfg.log_dir))
            self.journal_window.followup.connect(self.ask_journal)
        self.journal_window.open()

    def ask_journal(self, thread_id: str, question: str) -> None:
        """A follow-up in a reopened thread, about the screenshot saved with it."""
        w = self.journal_window
        thread = next((t for t in w.journal.threads() if t.id == thread_id), None)
        snap = w.journal.snapshot(thread.last) if thread else None
        if snap is None:
            return w.show_error("That screenshot is gone, so there is nothing to ask about.")
        self.journal_request += 1
        jid = self.journal_request
        history = thread.history(HISTORY_TURNS)
        w.show_thinking(question)

        def on_text(text: str) -> None:  # worker thread
            if jid != self.journal_request:
                raise Cancelled
            self.bus.journal_partial.emit((jid, question, text))

        def work():
            lines = []
            if self.ocr is not None and self.ocr.available:
                try:
                    lines = self.ocr.read(snap.image)
                except Exception:  # noqa: BLE001
                    lines = []
            prep = prepare(snap, hires=self.cfg.hires)
            return prep, lines, self.brain.ask(prep, lines, question, history, on_text=on_text)

        future = self.pool.submit(work)
        future.add_done_callback(lambda f: self.bus.journal_ready.emit((jid, thread_id, question, snap, f)))

    def _on_journal_partial(self, payload) -> None:
        jid, question, text = payload
        if jid == self.journal_request and self.journal_window is not None:
            self.journal_window.show_partial(question, text)

    def _on_journal_answer(self, payload) -> None:
        jid, thread_id, question, snap, future = payload
        w = self.journal_window
        if jid != self.journal_request or w is None:
            return
        try:
            prep, lines, answer = future.result()
        except BrainError as exc:
            return w.show_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Unexpected error while answering from the journal")
            return w.show_error(f"Something went wrong: {exc!r}")
        targets = resolve_points(prep, snap, lines, answer.points)
        try:
            self.log.add(question, answer.text, prep.full, answer.model, thread=thread_id, snap=snap, points=targets)
        except OSError as exc:
            log.error("Could not write the journal: %s", exc)
            return w.show_error(f"Answered, but could not save it: {exc}")
        w.show_answer(self.log.last_entry)

    # setup check ------------------------------------------------------------------------------

    def setup_checks(self):
        problem = self.transcriber.problem if self.transcriber is not None and not self.transcriber.available else None
        ocr = (self.ocr is not None and self.ocr.available) if self.cfg.ocr_enabled else None
        return run_checks(self.cfg, self.probes, voice_problem=problem, ocr_available=ocr)

    def maybe_show_setup(self) -> None:
        """At launch: the setup check on first run, or when something required is missing."""
        checks = self.setup_checks()
        if self.store.first_run() or needs_attention(checks):
            self.open_setup(checks)

    def open_setup(self, checks=None) -> None:
        if self.setup_window is None:
            w = self.setup_window = SetupWindow()
            # Kept on self: Qt holds a slot's object weakly, so a local Fixer would be collected.
            self._fixer = Fixer(self.probes, self.open_settings)
            w.fix_requested.connect(self._fixer.fix)
            w.recheck_requested.connect(self._refresh_setup)
            w.restart_requested.connect(restart)
            w.done.connect(self._setup_done)
        self.setup_window.show_checks(checks or self.setup_checks(), host_app(), *self._shortcut_labels())
        self.setup_window.open()

    def _setup_done(self) -> None:
        if self.store.first_run():
            try:
                self.store.save({})  # seen once; from now on only shown when something is missing
            except OSError as exc:
                log.warning("Could not save settings: %s", exc)

    def reload_settings(self) -> None:
        """Read every layer again (keeping command-line switches) and apply what changed."""
        cli = {k for k, v in self.cfg.sources.items() if v == "command line"}
        new = load_config(
            demo="demo" in cli,
            no_hotkey="hotkey_enabled" in cli,
            no_ocr="ocr_enabled" in cli,
            no_voice="voice_enabled" in cli,
            store=self.store,
            keychain=self.keychain,
        )
        self.apply_config(new)

    def apply_config(self, new: Config) -> None:
        """Switch to `new`, rebuilding only the services whose settings changed."""
        old, self.cfg = self.cfg, new
        changed = {k for k in vars(new) if k != "sources" and getattr(old, k) != getattr(new, k)}
        if changed & BRAIN_KEYS:
            self.brain = self.factories.brain(new)
        if "ocr_enabled" in changed:
            self.ocr = self.factories.ocr(new)
        if changed & {"voice_enabled", "whisper_model"}:
            self.transcriber = self.factories.transcriber(new)
            self._show_voice_availability()
            if self.transcriber is not None and self.transcriber.available:
                self.pool.submit(self._warm_voice)
        if "log_dir" in changed:
            self.log = DoubtLog(new.log_dir)
            if self.journal_window is not None:
                self.journal_window.journal = Journal(new.log_dir)
                self.journal_window.thread = None
        if changed & {"log_dir", "log_level"}:
            setup_logging(new.log_dir, new.log_level.upper())
        if changed & HOTKEY_KEYS or self.hotkey is None:
            self._start_hotkeys()
        self._show_hotkeys()
        log.info("Settings applied%s", f": {', '.join(sorted(changed))}" if changed else " (nothing changed)")

    def _warm_voice(self) -> None:
        try:
            self.transcriber.warm()
        except Exception as exc:  # noqa: BLE001
            log.error("Could not load the speech model '%s': %s", self.cfg.whisper_model, exc)

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
        self.orb.set_busy(False)  # ...so nobody is waiting on it any more
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
            self.snapshot = None  # never answer a later question about the previous screen
            log.warning("Screen capture failed: %s", exc)
            self.bubble.show_error(
                "Couldn't see your screen",
                str(exc),
                [("Open setup check", self.open_setup), ("Try again", lambda: self.start_ask(at_cursor=False))],
            )
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

    def _voice_key_down(self) -> None:
        """Hold to talk: ask about where the mouse is, and listen while the key is held."""
        self._holding, self._hold_t0 = True, time.monotonic()
        self.start_voice(at_cursor=True)

    def _voice_key_up(self) -> None:
        if not self._holding:
            return
        self._holding = False
        if time.monotonic() - self._hold_t0 < TAP_S:
            self.listenbox.release_hold()  # a tap: keep listening until a pause, like the orb
        else:
            self.listenbox.finish()  # let go: that was the question

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
        # Still holding the voice key (it may have been let go during the capture delay): until release.
        self.listenbox.open_at(pos, screen, lambda: self.recorder.level, hold=self._holding)

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
        self._end_thread()

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
            log.warning("Answer failed: %s", exc)
            self.bubble.show_error(question, str(exc), self._recovery(exc.action, question))
            self._show_bubble_near(cursor, [])
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("Unexpected error while answering")
            self.bubble.show_error(
                question,
                f"Something went wrong ({type(exc).__name__}). It's in the log; trying again usually works.",
                self._recovery("retry", question),
            )
            self._show_bubble_near(cursor, [])
            return

        u = answer.usage
        log.debug(
            "answered",
            extra={
                "model": answer.model,
                "first_text_s": answer.first_text,
                "seconds": round(answer.elapsed, 2),
                "points": len(answer.points),
                "ocr_lines": len(lines),
                "input_tokens": u.input_tokens if u else None,
                "output_tokens": u.output_tokens if u else None,
                "cache_read": u.cache_read if u else None,
            },
        )

        targets = resolve_points(prep, snap, lines, answer.points)
        self._last_pointing = (QRect(*snap.screen_geo), cursor, targets)
        self.overlay.point_to(QRect(*snap.screen_geo), cursor, targets)
        # The footer says what matters to a reader; the numbers matter to a tinkerer, so they're a hover away.
        details = [answer.model]
        if answer.first_text is not None:
            details.append(f"first words after {answer.first_text:.1f} s")
        details.append(f"done after {answer.elapsed:.1f} s")
        if lines:
            details.append(f"{len(lines)} OCR lines read")
        self.bubble.show_answer(
            question, answer.text, f"Answered in {answer.elapsed:.1f} s", ", ".join(details), len(targets)
        )
        keep_clear = []
        for x, y, _ in targets:  # the ring and the label that floats above-right of it
            keep_clear += [QPoint(int(x), int(y)), QPoint(int(x) + 90, int(y) - 34), QPoint(int(x) + 180, int(y) - 34)]
        self._show_bubble_near(cursor, keep_clear)

        self.history = (self.history + [(question, answer.text)])[-HISTORY_TURNS:]
        try:
            self.log.add(
                question, answer.text, prep.full, answer.model, thread=self.thread_id, snap=snap, points=targets
            )
            if not self.thread_id and self.log.last_entry is not None:
                self.thread_id = self.log.last_entry.id
        except OSError as exc:
            log.error("Could not write the journal: %s", exc)
        if self.cfg.save_cases:
            try:
                self.log.save_case(snap, question, answer.text, targets)
            except OSError as exc:
                log.error("Could not save the eval case: %s", exc)

    def _recovery(self, action: str | None, question: str):
        """The buttons an error offers: its likely fix first."""
        if action == "retry":
            return [("Try again", lambda: self.ask(question))]
        if action == "settings":
            return [("Open Settings", self.open_settings)]
        return []  # nothing to press: the follow-up field stays, to ask it another way

    def replay_markers(self) -> None:
        if self._last_pointing is not None:
            self.overlay.point_to(*self._last_pointing)

    def _followup(self, question: str) -> None:
        # Re-capture first: the lecture or page may have moved on since the last question.
        pos = self.last_rest
        self._capture(pos, then=lambda: self.ask(question))

    def _end_thread(self) -> None:
        self.request_id += 1
        self._drop_partial()
        self.history.clear()
        self.thread_id = ""
        self._last_pointing = None
        self.overlay.clear()
        self.orb.set_busy(False)

    def _screen_near(self, pos: QPoint) -> QRect:
        """The screen the current question is about; without a screenshot, the one under `pos`."""
        if self.snapshot is not None:
            return QRect(*self.snapshot.screen_geo)
        screen = QGuiApplication.screenAt(pos) or self.orb.screen()
        return screen.geometry()

    def _keep_bubble_on_screen(self) -> None:
        """A streaming bubble grows downwards; slide it up rather than let it run off the screen."""
        screen = self._screen_near(self.bubble.frameGeometry().center())
        g = self.bubble.frameGeometry()
        if g.bottom() > screen.bottom() - 12:
            self.bubble.move(g.x(), max(screen.top() + 12, screen.bottom() - 12 - g.height()))

    def _show_bubble_near(self, cursor: QPoint, targets: list[QPoint]) -> None:
        screen = self._screen_near(cursor)
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


def use_xwayland(env=os.environ) -> bool:
    """On Wayland, run Qt through XWayland so the orb, bubble and markers can be placed (ADR 0024).

    Native Wayland ignores window positions, which an overlay can't live without. Screenshots and
    shortcuts still go through the portal. Set QT_QPA_PLATFORM yourself to choose otherwise.
    """
    if env.get("XDG_SESSION_TYPE") == "wayland" and env.get("DISPLAY") and not env.get("QT_QPA_PLATFORM"):
        env["QT_QPA_PLATFORM"] = "xcb"
        return True
    return False


def restart() -> None:
    """Start a fresh copy of the app, then quit this one (a new Screen Recording grant needs it)."""
    if getattr(sys, "frozen", False):
        QProcess.startDetached(sys.executable, sys.argv[1:])
    else:
        QProcess.startDetached(sys.executable, ["-m", "marginalia", *sys.argv[1:]])
    QApplication.quit()


def hard_exit(code: int) -> None:
    """End the process now. sys.exit would first wait for every busy worker thread."""
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="marginalia", description="Screen-aware study companion.")
    ap.add_argument("--demo", action="store_true", help="canned answers, no API key needed")
    ap.add_argument("--no-hotkey", action="store_true", help="disable the global shortcut (use the orb)")
    ap.add_argument("--no-ocr", action="store_true", help="skip OCR even if it is installed")
    ap.add_argument("--no-voice", action="store_true", help="disable asking by voice")
    args = ap.parse_args(argv)

    setup_logging()  # console only, so problems reading the config are reported
    cfg = load_config(demo=args.demo, no_hotkey=args.no_hotkey, no_ocr=args.no_ocr, no_voice=args.no_voice)
    setup_logging(cfg.log_dir, cfg.log_level.upper())
    reporter = CrashReporter(cfg.log_dir)
    reporter.install()
    reporter.collect_fatal()
    if sys.platform.startswith("linux") and use_xwayland():
        log.info("Wayland session: windows run through XWayland; screenshots and shortcuts use the portal.")
    if sys.platform == "win32":
        try:  # group our windows under our own taskbar icon, not python.exe's
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Marginalia.Marginalia")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Marginalia")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C in the terminal quits

    if not cfg.demo and not cfg.api_key:
        log.warning("No API key found. Paste one in Settings (right-click the orb), or run with --demo.")

    controller = Controller(cfg)
    app.aboutToQuit.connect(controller.stop)
    controller.start()
    controller.maybe_show_setup()
    controller.offer_crash_reports(reporter)
    controller.check_for_updates()
    # Workers may still be downloading the speech model or waiting on an abandoned answer; nothing
    # they hold needs saving (the journal is written on this thread), so don't wait for them.
    hard_exit(app.exec())
