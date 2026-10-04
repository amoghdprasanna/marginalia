"""Small building blocks shared by the panels: pill chips, icon buttons, the level wave, the slate panel."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QLabel,
    QLineEdit,
    QWidget,
)

from .paint import draw_icon
from .theme import (
    AMBER,
    AMBER_HEX,
    EDGE,
    FLOATING,
    MUTED_HEX,
    SLATE,
    SLATE_HEX,
    TEXT,
    TEXT_HEX,
    keep_visible,
)


class Chip(QAbstractButton):
    """Pill button: line icon, label, and a keycap that shows its shortcut."""

    def __init__(self, icon: str, text: str, key: str) -> None:
        super().__init__()
        self.icon, self.key = icon, key
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        f = self.font()
        f.setPixelSize(13)
        f.setWeight(QFont.Medium)
        self.setFont(f)
        self.setFixedHeight(40)

    def sizeHint(self):  # noqa: N802
        fm = QFontMetricsF(self.font())
        return QSize(int(42 + fm.horizontalAdvance(self.text()) + 12 + 22 + 10), 40)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isEnabled()
        hot = on and (self.underMouse() or self.hasFocus())
        bg = QColor(AMBER) if hot else QColor(255, 255, 255)
        bg.setAlpha(42 if hot else (16 if on else 6))
        p.setPen(QPen(QColor(255, 178, 36, 90) if hot else EDGE, 1))
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        fg = AMBER if hot else (TEXT if on else QColor(MUTED_HEX))
        draw_icon(p, self.icon, QRectF(13, self.height() / 2 - 9, 18, 18), fg)
        p.setPen(fg)
        p.setFont(self.font())
        p.drawText(QRectF(40, 0, self.width() - 40, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        kf = QFont(self.font())
        kf.setPixelSize(10)
        kf.setWeight(QFont.DemiBold)
        cap = QRectF(self.width() - 32, self.height() / 2 - 10, 20, 20)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(255, 255, 255, 10))
        p.drawRoundedRect(cap, 5, 5)
        p.setPen(QColor(MUTED_HEX))
        p.setFont(kf)
        p.drawText(cap, Qt.AlignCenter, self.key)


class IconButton(QAbstractButton):
    """Round icon-only button for text fields (mic, send)."""

    def __init__(self, icon: str, tip: str, size: int = 28) -> None:
        super().__init__()
        self.icon = icon
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(size, size)
        self.filled = False  # amber disc, for the primary action

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hot = self.isEnabled() and self.underMouse()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.filled and self.isEnabled():
            p.setPen(Qt.NoPen)
            p.setBrush(AMBER.lighter(112) if hot else AMBER)
            p.drawEllipse(r)
            fg = QColor(SLATE_HEX)
        else:
            if hot:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 178, 36, 40))
                p.drawEllipse(r)
            fg = AMBER if hot else (QColor(MUTED_HEX) if self.isEnabled() else QColor(255, 255, 255, 50))
        pad = self.width() * 0.24
        draw_icon(p, self.icon, r.adjusted(pad, pad, -pad, -pad), fg)


class Wave(QWidget):
    """Rolling bars of recent mic level."""

    BARS = 40

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(26)
        self.levels = [0.0] * self.BARS
        self.live = True

    def push(self, level: float) -> None:
        self.levels = self.levels[1:] + [min(level * 18, 1.0) ** 0.6]
        self.update()

    def reset(self) -> None:
        self.levels = [0.0] * self.BARS
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        step = self.width() / self.BARS
        bw = max(2.0, step * 0.5)
        mid = self.height() / 2
        for i, v in enumerate(self.levels):
            c = QColor(AMBER) if self.live else QColor(MUTED_HEX)
            c.setAlpha(int(90 + 165 * (i / self.BARS)))  # newest bars brightest
            h = max(3.0, v * self.height())
            p.setBrush(c)
            p.drawRoundedRect(QRectF(i * step + (step - bw) / 2, mid - h / 2, bw, h), bw / 2, bw / 2)


class Panel(QWidget):
    """Frameless rounded slate panel shared by the ask box and the bubble."""

    radius = 14

    def __init__(self) -> None:
        super().__init__(None, FLOATING)
        self.setAttribute(Qt.WA_TranslucentBackground)
        keep_visible(self)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(EDGE, 1))
        p.setBrush(SLATE)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.radius, self.radius)


def line_edit(placeholder: str, size: int) -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setStyleSheet(
        f"QLineEdit {{ background: transparent; border: none; color: {TEXT_HEX}; font-size: {size}px;"
        f" selection-background-color: {AMBER_HEX}; selection-color: {SLATE_HEX}; }}"
    )
    pal = e.palette()
    pal.setColor(QPalette.PlaceholderText, QColor(MUTED_HEX))
    e.setPalette(pal)
    return e


def muted(text: str = "", size: int = 11) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(f"color: {MUTED_HEX}; font-size: {size}px; background: transparent;")
    return lab


def hints(*pairs: tuple[str, str]) -> QLabel:
    """Muted row like 'Enter ask  ·  Esc close', with the keys a shade brighter."""
    lab = muted()
    lab.setTextFormat(Qt.RichText)
    set_hints(lab, *pairs)
    return lab


def set_hints(lab: QLabel, *pairs: tuple[str, str]) -> None:
    dot = f"<span style='color:{MUTED_HEX}'>&nbsp;&nbsp;\u00b7&nbsp;&nbsp;</span>"
    lab.setText(dot.join(f"<span style='color:#C4CADB; font-weight:600'>{k}</span>&nbsp;{v}" for k, v in pairs))
