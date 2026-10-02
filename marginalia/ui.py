"""Overlay windows: the floating orb, the ask box, the answer bubble and the pointer layer.

Visual language: a quiet slate glass for text, and one amber "qubit" mark (a ring with an
equator and a state dot riding it) that is the only thing allowed to move or shout.
"""
from __future__ import annotations

import math
import sys

from PySide6.QtCore import QElapsedTimer, QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

SLATE = QColor(27, 32, 49, 246)
EDGE = QColor(255, 255, 255, 34)
TEXT = QColor(236, 239, 247)
AMBER = QColor(255, 178, 36)
HALO = QColor(10, 12, 22, 120)
PILL = QColor(27, 32, 49, 228)
TEXT_HEX, MUTED_HEX, AMBER_HEX, SLATE_HEX = "#ECEFF7", "#9BA3BC", "#FFB224", "#1B2031"

FLOATING = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool


def keep_visible(w: QWidget) -> None:
    """macOS hides Qt.Tool windows whenever the app loses focus; ours must stay on screen."""
    w.setAttribute(Qt.WA_MacAlwaysShowToolWindow)


def _activate_app_macos() -> None:
    """A Python process started from a terminal is a background app; pull it to the front."""
    try:
        from AppKit import NSApplication, NSApplicationActivateIgnoringOtherApps, NSRunningApplication

        NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:  # noqa: BLE001
        pass


def bring_to_front(w: QWidget) -> None:
    """Give a window keyboard focus even though another app is in front."""
    if sys.platform == "darwin":
        _activate_app_macos()
    w.show()
    w.raise_()
    w.activateWindow()
    if sys.platform == "win32":
        try:  # Windows refuses focus steals from background apps unless a key event just happened.
            import ctypes

            user32 = ctypes.windll.user32
            user32.keybd_event(0x12, 0, 0, 0)  # Alt down
            user32.keybd_event(0x12, 0, 2, 0)  # Alt up
            user32.SetForegroundWindow(int(w.winId()))
        except Exception:  # noqa: BLE001
            pass


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


class _Chip(QAbstractButton):
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


class _IconButton(QAbstractButton):
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


class _Wave(QWidget):
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


def _ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


class PointerOverlay(QWidget):
    """Full-screen, click-through layer that flies amber markers to the targets."""

    TRAVEL = 0.65  # s per marker
    STAGGER = 0.14  # s between markers
    SETTLE = 2.4  # s the state dot keeps orbiting after arrival, then everything rests

    def __init__(self) -> None:
        super().__init__(None, FLOATING | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        keep_visible(self)
        self.origin = QPointF()
        self.targets: list[tuple[QPointF, str]] = []
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
        if not self.targets:
            self.clear()
            return
        self.frozen_at = None
        self.clock.restart()
        self.tick.start()
        self.show()
        self.raise_()

    def clear(self) -> None:
        self.targets = []
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

    def _label(self, p: QPainter, at: QPointF, text: str, bounds: QRectF) -> None:
        """Label sits above and to the right of the ring, so the target line stays readable."""
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        fm = QFontMetricsF(f)
        w, h = fm.horizontalAdvance(text) + 22, fm.height() + 10
        x = at.x() + 10
        if x + w > bounds.right() - 8:
            x = at.x() - 10 - w
        y = at.y() - 22 - h
        if y < bounds.top() + 8:
            y = at.y() + 22
        r = QRectF(x, y, w, h)
        p.setPen(QPen(EDGE, 1))
        p.setBrush(PILL)
        p.drawRoundedRect(r, h / 2, h / 2)
        p.setPen(TEXT)
        p.drawText(r, Qt.AlignCenter, text)


class _Panel(QWidget):
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


def _line_edit(placeholder: str, size: int) -> QLineEdit:
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


def _muted(text: str = "", size: int = 11) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(f"color: {MUTED_HEX}; font-size: {size}px; background: transparent;")
    return lab


def _hints(*pairs: tuple[str, str]) -> QLabel:
    """Muted row like 'Enter ask  ·  Esc close', with the keys a shade brighter."""
    lab = _muted()
    lab.setTextFormat(Qt.RichText)
    set_hints(lab, *pairs)
    return lab


def set_hints(lab: QLabel, *pairs: tuple[str, str]) -> None:
    dot = f"<span style='color:{MUTED_HEX}'>&nbsp;&nbsp;\u00b7&nbsp;&nbsp;</span>"
    lab.setText(dot.join(f"<span style='color:#C4CADB; font-weight:600'>{k}</span>&nbsp;{v}" for k, v in pairs))


class AskBox(_Panel):
    submitted = Signal(str)
    cancelled = Signal()
    voice_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(460)
        self.edit = _line_edit("Ask about what's on your screen", 15)
        self.mic = _IconButton("mic", "Ask by voice instead")
        self.mic.clicked.connect(self._to_voice)
        self.hint = _hints(("Enter", "ask"), ("Esc", "close"))
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.edit, 1)
        row.addWidget(self.mic)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(50, 12, 12, 12)
        lay.setSpacing(4)
        lay.addLayout(row)
        lay.addWidget(self.hint)
        self.edit.returnPressed.connect(self._submit)

    def set_voice_available(self, ok: bool) -> None:
        self.mic.setVisible(ok)

    def _to_voice(self) -> None:
        self.hide()
        self.voice_requested.emit()

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        p = QPainter(self)
        draw_qubit(p, QPointF(27, 26), 9, 0.9, halo=False)

    def open_at(self, cursor: QPoint, screen: QRect) -> None:
        self.edit.clear()
        self.adjustSize()
        x = min(max(cursor.x() + 18, screen.left() + 12), screen.right() - self.width() - 12)
        y = cursor.y() + 24
        if y + self.height() > screen.bottom() - 12:
            y = cursor.y() - 24 - self.height()
        self.move(x, y)
        bring_to_front(self)
        self.edit.setFocus()

    def _submit(self) -> None:
        q = self.edit.text().strip()
        if q:
            self.hide()
            self.submitted.emit(q)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.hide()
            self.cancelled.emit()
        else:
            super().keyPressEvent(e)

    def changeEvent(self, e) -> None:  # noqa: N802
        # Clicking elsewhere abandons the question, as Esc does.
        if e.type() == QEvent.ActivationChange and self.isVisible() and not self.isActiveWindow():
            self.hide()
            self.cancelled.emit()
        super().changeEvent(e)


class AnswerBubble(_Panel):
    closed = Signal()
    followup = Signal(str)
    voice_followup = Signal()

    MAX_BODY = 400

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(440)
        self._drag: QPoint | None = None
        self._markdown = ""

        self.title = _muted("", 12)
        self.title.setStyleSheet(f"color: {MUTED_HEX}; font-size: 12px; font-weight: 600; background: transparent;")
        self.close_btn = QToolButton()
        self.close_btn.setText("\u2715")
        self.close_btn.setToolTip("Close (Esc). Ends this thread.")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(
            f"QToolButton {{ color: {MUTED_HEX}; background: transparent; border: none; font-size: 13px; padding: 2px 4px; }}"
            f"QToolButton:hover {{ color: {TEXT_HEX}; }}"
        )
        self.close_btn.clicked.connect(self.dismiss)

        self.status = QLabel()
        self.status.setStyleSheet(f"color: {TEXT_HEX}; font-size: 14px; background: transparent;")
        self._dots = 0
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(380)
        self._dot_timer.timeout.connect(self._tick_dots)

        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(True)
        self.body.setFrameShape(QTextBrowser.NoFrame)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body.setStyleSheet(
            f"QTextBrowser {{ background: transparent; border: none; color: {TEXT_HEX}; font-size: 14px; }}"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,60); border-radius: 4px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        pal = self.body.palette()
        pal.setColor(QPalette.Link, AMBER)
        pal.setColor(QPalette.Text, TEXT)
        self.body.setPalette(pal)

        self.meta = _muted("", 11)
        self.copy_btn = QToolButton()
        self.copy_btn.setText("Copy")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setStyleSheet(
            f"QToolButton {{ color: {MUTED_HEX}; background: transparent; border: none; font-size: 11px; }}"
            f"QToolButton:hover {{ color: {AMBER_HEX}; }}"
        )
        self.copy_btn.clicked.connect(self._copy)

        self.follow = _line_edit("Ask a follow-up", 13)
        self.follow.returnPressed.connect(self._followup)
        self.follow_mic = _IconButton("mic", "Ask the follow-up by voice", 26)
        self.follow_mic.clicked.connect(self.voice_followup.emit)
        self.follow_send = _IconButton("send", "Send (Enter)", 26)
        self.follow_send.filled = True
        self.follow_send.clicked.connect(self._followup)
        self.follow_send.setEnabled(False)
        self.follow.textChanged.connect(lambda t: self.follow_send.setEnabled(bool(t.strip())))
        self.follow_wrap = QWidget()
        self.follow_wrap.setObjectName("followWrap")
        self.follow_wrap.setAttribute(Qt.WA_StyledBackground)
        self.follow_wrap.setStyleSheet(
            "#followWrap { background: rgba(255,255,255,14); border: 1px solid rgba(255,255,255,22);"
            " border-radius: 10px; }"
        )
        fl = QHBoxLayout(self.follow_wrap)
        fl.setContentsMargins(12, 4, 4, 4)
        fl.setSpacing(2)
        fl.addWidget(self.follow, 1)
        fl.addWidget(self.follow_mic)
        fl.addWidget(self.follow_send)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addSpacing(20)  # room for the painted qubit mark
        head.addWidget(self.title, 1)
        head.addWidget(self.close_btn)
        foot = QHBoxLayout()
        foot.addWidget(self.meta, 1)
        foot.addWidget(self.copy_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 14, 14)
        lay.setSpacing(8)
        lay.addLayout(head)
        lay.addWidget(self.status)
        lay.addWidget(self.body)
        lay.addLayout(foot)
        lay.addWidget(self.follow_wrap)

    # states ---------------------------------------------------------------------------------

    def set_voice_available(self, ok: bool) -> None:
        self.follow_mic.setVisible(ok)

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        p = QPainter(self)
        draw_qubit(p, QPointF(25, 21), 6.5, 0.9, halo=False)

    def _set_title(self, question: str) -> None:
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(question, Qt.ElideRight, self.width() - 100))
        self.title.setToolTip(question)

    def show_thinking(self, question: str) -> None:
        self._set_title(question)
        self.body.hide()
        self.meta.hide()
        self.copy_btn.hide()
        self.follow_wrap.hide()
        self.status.show()
        self._dots = 0
        self._tick_dots()
        self._dot_timer.start()
        self.adjustSize()

    def show_answer(self, question: str, markdown: str, meta: str) -> None:
        self._dot_timer.stop()
        self._set_title(question)
        self._markdown = markdown
        self.status.hide()
        self.body.setMarkdown(markdown)
        self._space_paragraphs()
        self.body.show()
        self.meta.setText(meta)
        self.meta.show()
        self.copy_btn.setText("Copy")
        self.copy_btn.show()
        self.follow.clear()
        self.follow_wrap.show()
        self._fit()

    def show_error(self, question: str, message: str) -> None:
        self.show_answer(question, message, "Nothing was sent to the log.")
        self.copy_btn.hide()

    def _space_paragraphs(self) -> None:
        from PySide6.QtGui import QTextCursor

        from PySide6.QtGui import QTextBlockFormat

        cur = QTextCursor(self.body.document())
        cur.select(QTextCursor.Document)
        fmt = QTextBlockFormat()
        fmt.setBottomMargin(7)
        fmt.setLineHeight(118, 1)  # 1 = ProportionalHeight
        cur.mergeBlockFormat(fmt)

    def _fit(self) -> None:
        doc = self.body.document()
        doc.setTextWidth(self.width() - 32 - 2 * doc.documentMargin())
        h = int(doc.size().height()) + 8
        self.body.setFixedHeight(max(28, min(h, self.MAX_BODY)))
        self.adjustSize()

    def _tick_dots(self) -> None:
        self._dots = (self._dots % 3) + 1
        self.status.setText("Reading your screen" + "." * self._dots)

    # actions --------------------------------------------------------------------------------

    def dismiss(self) -> None:
        self._dot_timer.stop()
        self.hide()
        self.closed.emit()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._markdown)
        self.copy_btn.setText("Copied")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText("Copy"))

    def _followup(self) -> None:
        q = self.follow.text().strip()
        if q:
            self.followup.emit(q)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(e)

    # drag by the header ----------------------------------------------------------------------

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton and e.position().y() < 40:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802
        self._drag = None


class ModeChooser(_Panel):
    """Pops out of the orb on click: ask by typing or by voice."""

    chosen = Signal(str)  # "type" or "voice"

    def __init__(self) -> None:
        super().__init__()
        self.radius = 14
        self.label = _muted("Ask about the screen", 11)
        self.label.setStyleSheet(f"color: {MUTED_HEX}; font-size: 11px; font-weight: 600; background: transparent;")
        self.type_btn = _Chip("keys", "Type", "T")
        self.voice_btn = _Chip("mic", "Speak", "V")
        self.type_btn.setToolTip("Type the question (T or Enter)")
        self.voice_btn.setToolTip("Say the question (V or Space)")
        self.type_btn.clicked.connect(lambda: self._pick("type"))
        self.voice_btn.clicked.connect(lambda: self._pick("voice"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.type_btn)
        row.addWidget(self.voice_btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(7)
        lay.addWidget(self.label)
        lay.addLayout(row)
        self.label.setContentsMargins(4, 0, 0, 0)

    def set_voice_available(self, ok: bool, why: str = "") -> None:
        self.voice_btn.setEnabled(ok)
        self.voice_btn.setToolTip("Say the question (V or Space)" if ok else f"Voice is off: {why}")

    def open_beside(self, anchor: QRect, screen: QRect) -> None:
        self.adjustSize()
        gap = 10
        x = anchor.left() - gap - self.width() if anchor.center().x() > screen.center().x() else anchor.right() + gap
        y = anchor.center().y() - self.height() // 2
        x = min(max(x, screen.left() + 8), screen.right() - self.width() - 8)
        y = min(max(y, screen.top() + 8), screen.bottom() - self.height() - 8)
        self.move(x, y)
        bring_to_front(self)

    def _pick(self, mode: str) -> None:
        self.hide()
        self.chosen.emit(mode)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        k = e.key()
        if k == Qt.Key_Escape:
            self.hide()
        elif k in (Qt.Key_T, Qt.Key_Return, Qt.Key_Enter):
            self._pick("type")
        elif k in (Qt.Key_V, Qt.Key_Space) and self.voice_btn.isEnabled():
            self._pick("voice")
        else:
            super().keyPressEvent(e)

    def changeEvent(self, e) -> None:  # noqa: N802
        if e.type() == QEvent.ActivationChange and self.isVisible() and not self.isActiveWindow():
            self.hide()
        super().changeEvent(e)


class ListenBox(_Panel):
    """Shows that the mic is live. A pause after speech ends it, as do Enter or a click."""

    stop_requested = Signal()
    cancelled = Signal()

    SILENCE_S = 1.4  # pause after speech that ends the question
    MAX_S = 45.0

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(400)
        self.status = QLabel()
        self.status.setStyleSheet(f"color: {TEXT_HEX}; font-size: 15px; font-weight: 500; background: transparent;")
        self.timer_lab = _muted("0:00", 11)
        self.wave = _Wave()
        self.send_btn = _IconButton("send", "Send now (Enter)", 30)
        self.send_btn.filled = True
        self.send_btn.clicked.connect(self._send)
        self.hint = _hints(("pause", "sends"), ("Enter", "send now"), ("Esc", "cancel"))
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
        self.clock = QElapsedTimer()
        self.tick = QTimer(self)
        self.tick.setInterval(33)
        self.tick.timeout.connect(self._on_tick)

    def open_at(self, cursor: QPoint, screen: QRect, level_fn) -> None:
        self.level_fn = level_fn
        self._listening = True
        self._floor: list[float] = []
        self._heard = False
        self._quiet_since: float | None = None
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
        QTimer.singleShot(2600, lambda: None if self._listening else self.hide())

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
        if t < 0.35:  # learn the room's noise floor before judging speech vs. silence
            self._floor.append(raw)
        else:
            floor = sum(self._floor) / len(self._floor) if self._floor else 0.0
            speaking = raw > max(3 * floor, 0.012)
            if speaking:
                self._heard, self._quiet_since = True, None
            elif self._heard:
                self._quiet_since = self._quiet_since or t
                if t - self._quiet_since >= self.SILENCE_S:
                    self._send()
            if t >= self.MAX_S:
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


class Orb(QWidget):
    """Small draggable launcher that hovers on screen. Click to choose type or voice; right-click for the menu."""

    clicked = Signal()
    voice_requested = Signal()
    type_requested = Signal()
    quit_requested = Signal()
    SIZE = 48

    def __init__(self, hotkey_text: str | None) -> None:
        super().__init__(None, FLOATING | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        keep_visible(self)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        tip = "Ask about what's on screen, by typing or by voice. It looks where your mouse last rested."
        if hotkey_text:
            tip += f"\nShortcut: {hotkey_text} asks about exactly where the mouse is."
        self.setToolTip(tip + "\nDrag to move, right-click to quit.")
        self._press: QPoint | None = None
        self._dragging = False
        self.phase = 0.9
        self._spin = QTimer(self)
        self._spin.setInterval(16)
        self._spin.timeout.connect(self._advance)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.SIZE - 18, screen.center().y())

    def set_busy(self, busy: bool) -> None:
        if busy:
            self._spin.start()
        else:
            self._spin.stop()
            self.phase = 0.9
            self.update()

    def _advance(self) -> None:
        self.phase += 0.12
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.SIZE / 2, self.SIZE / 2)
        p.setPen(QPen(EDGE, 1))
        p.setBrush(SLATE)
        p.drawEllipse(c, self.SIZE / 2 - 2, self.SIZE / 2 - 2)
        draw_qubit(p, c, 11, self.phase, halo=False)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._origin = self.pos()
            self._dragging = False

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._press is None:
            return
        delta = e.globalPosition().toPoint() - self._press
        if self._dragging or delta.manhattanLength() > 5:
            self._dragging = True
            self.move(self._origin + delta)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton and self._press is not None and not self._dragging:
            self.clicked.emit()
        self._press = None

    def contextMenuEvent(self, e) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.addAction("Ask by typing", self.type_requested.emit)
        menu.addAction("Ask by voice", self.voice_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit Marginalia", self.quit_requested.emit)
        menu.exec(e.globalPos())
