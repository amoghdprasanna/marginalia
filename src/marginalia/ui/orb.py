"""The small draggable launcher that hovers at the screen edge."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QMenu,
    QWidget,
)

from ..pointing import keep_on_screen
from .paint import draw_qubit
from .theme import (
    EDGE,
    FLOATING,
    SLATE,
    keep_visible,
)


class Orb(QWidget):
    """Small draggable launcher that hovers on screen. Click to choose type or voice; right-click for the menu."""

    clicked = Signal()
    voice_requested = Signal()
    type_requested = Signal()
    quit_requested = Signal()
    settings_requested = Signal()
    setup_requested = Signal()
    journal_requested = Signal()
    update_requested = Signal()
    check_updates_requested = Signal()
    SIZE = 48

    def __init__(self, hotkey_text: str | None, voice_hotkey_text: str | None = None) -> None:
        super().__init__(None, FLOATING | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        keep_visible(self)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.set_hotkeys(hotkey_text, voice_hotkey_text)
        self.update_version: str | None = None
        self._press: QPoint | None = None
        self._dragging = False
        self.phase = 0.9
        self._spin = QTimer(self)
        self._spin.setInterval(16)
        self._spin.timeout.connect(self._advance)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.SIZE - 18, screen.center().y())
        # Unplugging a monitor can leave the orb where no screen is; with no hotkey it is the only way in.
        # A bound method, so Qt disconnects it when the orb goes away.
        QGuiApplication.instance().screenRemoved.connect(self._screen_removed)

    def _screen_removed(self, _screen) -> None:
        QTimer.singleShot(0, self, self.rehome)  # after Qt has moved windows off the old screen

    def set_hotkeys(self, hotkey_text: str | None, voice_hotkey_text: str | None = None) -> None:
        tip = "Ask about what's on screen, by typing or by voice. It looks where your mouse last rested."
        if hotkey_text:
            tip += f"\nShortcut: {hotkey_text} asks about exactly where the mouse is."
        if voice_hotkey_text:
            tip += f"\nHold {voice_hotkey_text} and speak; let go to ask."
        self.setToolTip(tip + "\nDrag to move, right-click for settings and more.")

    def set_update(self, version: str | None) -> None:
        """A newer release exists: the menu offers it."""
        self.update_version = version

    def rehome(self) -> None:
        """Pull the orb wholly onto the nearest screen if any of it hangs off."""
        areas = [s.availableGeometry() for s in QGuiApplication.screens()]
        x, y = keep_on_screen(
            (self.x(), self.y()), (self.width(), self.height()), [(a.x(), a.y(), a.width(), a.height()) for a in areas]
        )
        self.move(x, y)

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
        if self._dragging:
            self.rehome()
        self._press = None

    def build_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction("Ask by typing", self.type_requested.emit)
        menu.addAction("Ask by voice", self.voice_requested.emit)
        menu.addSeparator()
        menu.addAction("Journal…", self.journal_requested.emit)
        menu.addAction("Settings…", self.settings_requested.emit)
        menu.addAction("Setup check…", self.setup_requested.emit)
        if self.update_version:
            menu.addAction(f"Update to {self.update_version}…", self.update_requested.emit)
        else:
            menu.addAction("Check for updates", self.check_updates_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit Marginalia", self.quit_requested.emit)
        return menu

    def contextMenuEvent(self, e) -> None:  # noqa: N802
        self.build_menu().exec(e.globalPos())
