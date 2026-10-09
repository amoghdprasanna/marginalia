"""Shows that the mic is live and decides, with SilenceDetector, when you have finished."""
from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from ..voice import SilenceDetector
from .paint import draw_qubit
from .theme import (
    AMBER,
    TEXT_HEX,
    bring_to_front,
)
from .widgets import IconButton, Panel, Wave, hints, muted, set_hints


class ListenBox(Panel):
    """Shows that the mic is live. A pause after speech ends it, as do Enter or a click."""

    stop_requested = Signal()
    cancelled = Signal()
    no_audio = Signal()  # the microphone delivered nothing at all

    NO_AUDIO_S = 2.5  # real microphones always pick up some noise; exact silence this long means no audio
    def __init__(self, detector: SilenceDetector | None = None) -> None:
        super().__init__()
        self.detector = detector or SilenceDetector()
        self.setFixedWidth(400)
        self.status = QLabel()
        self.status.setStyleSheet(f"color: {TEXT_HEX}; font-size: 15px; font-weight: 500; background: transparent;")
        self.timer_lab = muted("0:00", 11)
        self.device_lab = muted("", 11)
        self.device_lab.hide()
        self.wave = Wave()
        self.send_btn = IconButton("send", "Send now (Enter)", 30)
        self.send_btn.filled = True
        self.send_btn.clicked.connect(self._send)
        self.hint = hints(("pause", "sends"), ("Enter", "send now"), ("Esc", "cancel"))
        head = QHBoxLayout()
        head.addWidget(self.status, 1)
        head.addWidget(self.timer_lab)
        mid = QHBoxLayout()
        mid.setSpacing(10)
        mid.addWidget(self.wave, 1)
        mid.addWidget(self.send_btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(52, 12, 14, 12)
        lay.setSpacing(6)
        lay.addLayout(head)
        lay.addWidget(self.device_lab)
        lay.addLayout(mid)
        lay.addWidget(self.hint)
        self.level_fn = lambda: 0.0
        self.level = 0.0
        self.phase = 0.9
        self._listening = False
        self.hold = False
        self._loudest = 0.0
        self._session = 0  # bumped by open_at, so a timer from an earlier question can tell it is stale
        self.clock = QElapsedTimer()
        self.tick = QTimer(self)
        self.tick.setInterval(33)
        self.tick.timeout.connect(self._on_tick)

    def open_at(self, cursor: QPoint, screen: QRect, level_fn, hold: bool = False, device: str = "") -> None:
        """Start listening. With `hold`, a pause doesn't end it: releasing the voice key does."""
        self.level_fn = level_fn
        self._listening = True
        self._session += 1
        self.hold = hold
        self._loudest = 0.0
        self.detector.reset()
        self.status.setText("Listening…")
        self.status.setWordWrap(False)
        # Which microphone: macOS switches to AirPods or an iPhone on its own, and that's often why.
        self.device_lab.setText(device)
        self.device_lab.setVisible(bool(device))
        self.timer_lab.setText("0:00")
        self.timer_lab.show()
        self.wave.live = True
        self.wave.reset()
        self.wave.show()
        self.send_btn.show()
        self._set_listen_hints()
        self.adjustSize()
        x = min(max(cursor.x() + 18, screen.left() + 12), screen.right() - self.width() - 12)
        y = cursor.y() + 24
        if y + self.height() > screen.bottom() - 12:
            y = cursor.y() - 24 - self.height()
        self.move(x, y)
        self.clock.restart()
        self.tick.start()
        bring_to_front(self)

    def _set_listen_hints(self) -> None:
        if self.hold:
            set_hints(self.hint, ("release", "sends"), ("Esc", "cancel"))
        else:
            set_hints(self.hint, ("pause", "sends"), ("Enter", "send now"), ("Esc", "cancel"))

    def release_hold(self) -> None:
        """The voice key was only tapped: from now on a pause ends the question."""
        if self.hold:
            self.hold = False
            self._set_listen_hints()

    def finish(self) -> None:
        """Send what was said so far (the voice key was let go)."""
        self._send()

    def show_transcribing(self) -> None:
        self._listening = False
        self.level = 0.0
        self.status.setText("Transcribing…")
        self.wave.live = False
        self.wave.update()
        self.send_btn.hide()
        set_hints(self.hint, ("Esc", "cancel"))

    def show_problem(self, message: str) -> None:
        self._listening = False
        self.tick.stop()
        self.level = 0.0
        self.status.setText(message)
        self.status.setWordWrap(True)  # problems can be a sentence long; never cut them off
        self.device_lab.hide()
        self.timer_lab.hide()
        self.wave.hide()
        self.send_btn.hide()
        set_hints(self.hint, ("Orb", "try again"), ("Esc", "close"))
        self.adjustSize()
        self.update()
        # `self` as context: Qt cancels the timer if this widget is destroyed first. The session
        # check keeps it from hiding a question asked again since (it may be transcribing by then).
        session = self._session
        # Long enough to read: about 2.6 s, plus time for a longer message.
        stay = 2600 + 40 * max(0, len(message) - 30)
        QTimer.singleShot(stay, self, lambda: self.hide() if session == self._session else None)

    def close_quietly(self) -> None:
        self._listening = False
        self.tick.stop()
        self.hide()

    def _on_tick(self) -> None:
        self.phase += 0.12
        if not self._listening:
            self.update()
            return
        raw = self.level_fn()
        self._loudest = max(self._loudest, raw)
        self.level = 0.6 * self.level + 0.4 * raw
        self.wave.push(self.level)
        t = self.clock.elapsed() / 1000
        self.timer_lab.setText(f"{int(t) // 60}:{int(t) % 60:02d}")
        if t >= self.NO_AUDIO_S and self._loudest == 0.0:
            self._listening = False
            self.no_audio.emit()
            return
        done = self.detector.feed(t, raw)
        if done and (not self.hold or t >= self.detector.max_s):  # holding: only the time limit ends it
            self._send()
        self.update()

    def _send(self) -> None:
        if self._listening:
            self._listening = False
            self.stop_requested.emit()

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(27, 25)
        if self._listening:  # a soft disc that swells with the voice
            glow = QColor(AMBER)
            glow.setAlpha(46)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            rr = 13 + min(self.level * 220, 7)
            p.drawEllipse(c, rr, rr)
        draw_qubit(p, c, 9, self.phase, halo=False)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.close_quietly()
            self.cancelled.emit()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._send()
        else:
            super().keyPressEvent(e)
