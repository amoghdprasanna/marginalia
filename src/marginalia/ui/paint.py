"""The amber qubit mark and the line icons, drawn in code so they stay crisp at any size."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap

from .theme import (
    AMBER,
    HALO,
)


def draw_qubit(p: QPainter, c: QPointF, r: float, phase: float, halo: bool = True) -> None:
    """Ring, equator and a state dot; the dot dims when it is 'behind' the sphere."""
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(Qt.NoBrush)
    if halo:  # dark outline keeps the ring visible on white pages; the inside stays clear
        p.setPen(QPen(HALO, max(2.0, r / 5.5) + 4))
        p.drawEllipse(c, r, r)
    p.setPen(QPen(AMBER, max(2.0, r / 5.5)))
    p.drawEllipse(c, r, r)
    eq = QColor(AMBER)
    eq.setAlpha(120)
    p.setPen(QPen(eq, 1.2))
    p.drawEllipse(c, r, r * 0.34)
    dot = QColor(AMBER)
    dot.setAlpha(255 if math.sin(phase) >= 0 else 120)
    p.setPen(Qt.NoPen)
    p.setBrush(dot)
    p.drawEllipse(QPointF(c.x() + r * math.cos(phase), c.y() + r * 0.34 * math.sin(phase)), r / 4.4, r / 4.4)


def draw_icon(p: QPainter, kind: str, r: QRectF, color: QColor) -> None:
    """Line icons drawn in code, so they match the qubit and stay crisp: mic, keys, send."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = min(r.width(), r.height())
    cx, top = r.center().x(), r.center().y() - s / 2
    if kind == "mic":
        w, h = s * 0.36, s * 0.54
        p.drawRoundedRect(QRectF(cx - w / 2, top + s * 0.06, w, h), w / 2, w / 2)
        arc = QRectF(cx - s * 0.32, top + s * 0.18, s * 0.64, s * 0.58)
        p.drawArc(arc, 200 * 16, 140 * 16)
        p.drawLine(QPointF(cx, arc.bottom()), QPointF(cx, top + s * 0.94))
        p.drawLine(QPointF(cx - s * 0.16, top + s * 0.94), QPointF(cx + s * 0.16, top + s * 0.94))
    elif kind == "keys":
        body = QRectF(cx - s * 0.46, top + s * 0.2, s * 0.92, s * 0.6)
        p.drawRoundedRect(body, s * 0.1, s * 0.1)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        k = s * 0.075
        for row, y in enumerate((body.top() + s * 0.16, body.top() + s * 0.3)):
            for i in range(4 - row):
                x = body.left() + s * (0.17 + row * 0.1) + i * s * 0.2
                p.drawEllipse(QPointF(x, y), k, k)
        p.setPen(pen)
        p.drawLine(QPointF(cx - s * 0.2, body.bottom() - s * 0.14), QPointF(cx + s * 0.2, body.bottom() - s * 0.14))
    elif kind == "send":
        p.drawLine(QPointF(cx, top + s * 0.82), QPointF(cx, top + s * 0.2))
        p.drawLine(QPointF(cx - s * 0.28, top + s * 0.46), QPointF(cx, top + s * 0.18))
        p.drawLine(QPointF(cx + s * 0.28, top + s * 0.46), QPointF(cx, top + s * 0.18))
    p.restore()


def app_icon_image(size: int) -> QImage:
    """The app icon: the qubit on a slate disc. The build's icon files are drawn from this too."""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    margin = size * 0.09  # the macOS icon grid leaves a margin around the shape
    disc = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    p.setPen(QPen(QColor(255, 255, 255, 40), max(1.0, size / 256)))
    p.setBrush(QColor(27, 32, 49))
    p.drawEllipse(disc)
    draw_qubit(p, QPointF(size / 2, size / 2), disc.width() * 0.3, 0.9, halo=False)
    p.end()
    return img


def app_icon() -> QIcon:
    """For window title bars and the taskbar (Windows, Linux); macOS uses the bundle's icon."""
    icon = QIcon()
    for s in (16, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(app_icon_image(s)))
    return icon
