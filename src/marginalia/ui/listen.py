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

    def __init__(self, detector: SilenceDetector | None = None) -> None:
        super().__init__()
        self.detector = detector or SilenceDetector()
        self.setFixedWidth(400)
        self.status = QLabel()
        self.status.setStyleSheet(f"color: {TEXT_HEX}; font-size: 15px; font-weight: 500; background: transparent;")
        self.timer_lab = muted("0:00", 11)
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
        lay.addLayout(mid)
        lay.addWidget(self.hint)
        self.level_fn = lambda: 0.0
        self.level = 0.0
        self.phase = 0.9
        self._listening = False
        self._session = 0  # bumped by open_at, so a timer from an earlier question can tell it is stale
        self.clock = QElapsedTimer()
        self.tick = QTimer(self)
        self.tick.setInterval(33)
        self.tick.timeout.connect(self._on_tick)

    def open_at(self, cursor: QPoint, screen: QRect, level_fn) -> None:
        self.level_fn = level_fn
        self._listening = True
        self._session += 1
        self.detector.reset()
        self.status.setText("Listening…")
        self.timer_lab.setText("0:00")
        self.timer_lab.show()
        self.wave.live = True
        self.wave.reset()
        self.wave.show()
        self.send_btn.show()
        set_hints(self.hint, ("pause", "sends"), ("Enter", "send now"), ("Esc", "cancel"))
        self.adjustSize()
        x = min(max(cursor.x() + 18, screen.left() + 12), screen.right() - self.width() - 12)
        y = cursor.y() + 24
        if y + self.height() > screen.bottom() - 12:
            y = cursor.y() - 24 - self.height()
        self.move(x, y)
        self.clock.restart()
        self.tick.start()
        bring_to_front(self)

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
        self.timer_lab.hide()
        self.wave.hide()
        self.send_btn.hide()
        set_hints(self.hint, ("Orb", "try again"), ("Esc", "close"))
        self.adjustSize()
        self.update()
        # `self` as context: Qt cancels the timer if this widget is destroyed first. The session
        # check keeps it from hiding a question asked again since (it may be transcribing by then).
        session = self._session
        QTimer.singleShot(2600, self, lambda: self.hide() if session == self._session else None)

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
        self.level = 0.6 * self.level + 0.4 * raw
        self.wave.push(self.level)
        t = self.clock.elapsed() / 1000
        self.timer_lab.setText(f"{int(t) // 60}:{int(t) % 60:02d}")
        if self.detector.feed(t, raw):
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
