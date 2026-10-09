"""Full-screen click-through layer that flies amber markers to what the answer talks about."""
from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget,
)

from .paint import draw_qubit
from .theme import (
    AMBER,
    EDGE,
    FLOATING,
    PILL,
    TEXT,
    keep_visible,
)


def _ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


class PointerOverlay(QWidget):
    """Full-screen, click-through layer that flies amber markers to the targets."""

    TRAVEL = 0.65  # s per marker
    PULSE = 0.6  # s the arrival ring keeps growing
    STAGGER = 0.14  # s between markers
    SETTLE = 2.4  # s the state dot keeps orbiting after arrival, then everything rests

    def __init__(self) -> None:
        super().__init__(None, FLOATING | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        keep_visible(self)
        self.origin = QPointF()
        self.targets: list[tuple[QPointF, str]] = []
        self.hidden: set[int] = set()  # markers whose content has left the screen (tracking)
        self.clock = QElapsedTimer()
        self.frozen_at: float | None = None
        self.tick = QTimer(self)
        self.tick.setInterval(16)
        self.tick.timeout.connect(self._on_tick)

    def point_to(self, screen: QRect, origin: QPoint, targets: list[tuple[float, float, str]]) -> None:
        self.setGeometry(screen)
        off = QPointF(screen.topLeft())
        self.origin = QPointF(origin) - off
        self.targets = [(QPointF(x, y) - off, label) for x, y, label in targets]
        self.hidden = set()
        if not self.targets:
            self.clear()
            return
        self.frozen_at = None
        self.clock.restart()
        self.tick.start()
        self.show()
        self.raise_()

    def follow(self, positions: list[tuple[float, float, bool]]) -> None:
        """Tracking moved markers (global logical x, y), or hid them (visible False)."""
        off = QPointF(self.geometry().topLeft())
        for i, (x, y, visible) in enumerate(positions[: len(self.targets)]):
            self.targets[i] = (QPointF(x, y) - off, self.targets[i][1])
            (self.hidden.discard if visible else self.hidden.add)(i)
        self.update()

    def clear(self) -> None:
        self.targets = []
        self.hidden = set()
        self.tick.stop()
        self.hide()

    def _elapsed(self) -> float:
        return self.frozen_at if self.frozen_at is not None else self.clock.elapsed() / 1000

    def _on_tick(self) -> None:
        done = self.TRAVEL + self.STAGGER * (len(self.targets) - 1) + self.SETTLE
        if self.clock.elapsed() / 1000 > done:
            self.frozen_at = done
            self.tick.stop()
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self._elapsed()
        bounds = QRectF(self.rect())
        for i, (target, label) in enumerate(self.targets):
            if i in self.hidden:
                continue
            local = (t - i * self.STAGGER) / self.TRAVEL
            if local <= 0:
                continue
            k = _ease_out_cubic(min(local, 1.0))
            d = target - self.origin
            length = math.hypot(d.x(), d.y()) or 1.0
            ctrl = (self.origin + target) / 2 + QPointF(-d.y(), d.x()) * (0.18 * min(length, 600) / length)
            pos = (1 - k) ** 2 * self.origin + 2 * (1 - k) * k * ctrl + k * k * target

            if local < 1.0:  # fading trail while travelling
                trail = QColor(AMBER)
                trail.setAlpha(int(140 * (1 - k)))
                p.setPen(QPen(trail, 2, Qt.DotLine))
                p.setBrush(Qt.NoBrush)
                steps = 24
                prev = self.origin
                for s in range(1, steps + 1):
                    u = k * s / steps
                    q = (1 - u) ** 2 * self.origin + 2 * (1 - u) * u * ctrl + u * u * target
                    p.drawLine(prev, q)
                    prev = q

            since = (local - 1.0) * self.TRAVEL
            if 0 <= since < 0.6:  # arrival pulse
                pulse = QColor(AMBER)
                pulse.setAlpha(int(200 * (1 - since / 0.6)))
                p.setPen(QPen(pulse, 2))
                p.setBrush(Qt.NoBrush)
                rr = 15 + 22 * (since / 0.6)
                p.drawEllipse(pos, rr, rr)

            draw_qubit(p, pos, 15, t * 3.2 + i * 1.7)
            if local >= 1.0 and label:
                self._label(p, pos, label, bounds)

    def label_font(self) -> QFont:
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        f.setWeight(QFont.DemiBold)
        return f

    def label_rect(self, at: QPointF, text: str, bounds: QRectF) -> QRectF:
        """Above and to the right of the ring, so the target line stays readable; flipped at edges."""
        fm = QFontMetricsF(self.label_font())
        w, h = fm.horizontalAdvance(text) + 22, fm.height() + 10
        x = at.x() + 10
        if x + w > bounds.right() - 8:
            x = at.x() - 10 - w
        y = at.y() - 22 - h
        if y < bounds.top() + 8:
            y = at.y() + 22
        return QRectF(x, y, w, h)

    def _label(self, p: QPainter, at: QPointF, text: str, bounds: QRectF) -> None:
        p.setFont(self.label_font())
        r = self.label_rect(at, text, bounds)
        h = r.height()
        p.setPen(QPen(EDGE, 1))
        p.setBrush(PILL)
        p.drawRoundedRect(r, h / 2, h / 2)
        p.setPen(TEXT)
        p.drawText(r, Qt.AlignCenter, text)
