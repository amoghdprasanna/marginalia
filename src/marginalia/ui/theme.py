"""Colours, window flags and the platform tricks that keep floating windows on top."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget,
)

SLATE = QColor(27, 32, 49, 246)
EDGE = QColor(255, 255, 255, 34)
TEXT = QColor(236, 239, 247)
AMBER = QColor(255, 178, 36)
HALO = QColor(10, 12, 22, 120)
PILL = QColor(27, 32, 49, 228)
TEXT_HEX, MUTED_HEX, AMBER_HEX, SLATE_HEX = "#ECEFF7", "#9BA3BC", "#FFB224", "#1B2031"
ERROR_HEX = "#FF8A80"  # only for "this went wrong"; amber stays the colour of the answer's markers
OK_HEX = "#6ECC8C"  # the setup check's "ready"
DISABLED_HEX = "#6B7290"  # clearly fainter than muted text, so "can't use this" never looks like "secondary"
SIDEBAR_HEX = "#161A28"  # a shade under the slate: the Settings sidebar
CHECK_SIZE, CHECK_SPACING = 15, 8
CHECK_INDENT = CHECK_SIZE + CHECK_SPACING  # where a checkbox's words start: its help line lines up there

CHECK_ICON = (Path(__file__).parent / "assets" / "check.svg").as_posix()

# Ordinary windows (Settings, Setup, Journal): the same slate and amber, with native layout.
DIALOG_STYLE = f"""
QWidget {{ background: {SLATE_HEX}; color: {TEXT_HEX}; font-size: 13px; }}
QFrame#card {{ background: rgba(255,255,255,6); border: 1px solid rgba(255,255,255,24); border-radius: 10px; }}
QFrame#card QLabel, QFrame#card QCheckBox, QFrame#card QWidget#row {{ background: transparent; }}
QLabel#heading {{ font-size: 17px; font-weight: 600; padding-left: 2px; }}
QWidget#sidebar {{ background: {SIDEBAR_HEX}; border-right: 1px solid rgba(255,255,255,20); }}
QListWidget#nav {{ background: transparent; border: none; padding: 0; outline: 0; }}
QListWidget#nav::item {{ padding: 7px 10px; margin: 1px 0; border-radius: 6px; color: {TEXT_HEX}; }}
QListWidget#nav::item:hover {{ background: rgba(255,255,255,10); }}
QListWidget#nav::item:selected {{ background: rgba(255,255,255,26); color: {TEXT_HEX}; font-weight: 600; }}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget, QTextBrowser {{
    background: rgba(255,255,255,12); border: 1px solid rgba(255,255,255,30); border-radius: 7px;
    padding: 5px 8px; selection-background-color: {AMBER_HEX}; selection-color: {SLATE_HEX}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {AMBER_HEX}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QCheckBox:disabled,
QPlainTextEdit:disabled {{ color: {DISABLED_HEX}; }}
QComboBox QAbstractItemView {{ background: {SLATE_HEX}; selection-background-color: rgba(255,178,36,60); }}
QPushButton {{ background: rgba(255,255,255,16); border: 1px solid rgba(255,255,255,30); border-radius: 7px;
    padding: 6px 14px; }}
QPushButton:hover {{ border-color: {AMBER_HEX}; }}
QPushButton:focus {{ border: 2px solid {AMBER_HEX}; }}
QPushButton#primary {{ background: {AMBER_HEX}; color: {SLATE_HEX}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #FFC152; }}
QPushButton#primary:focus {{ border: 2px solid {TEXT_HEX}; }}
QCheckBox {{ spacing: {CHECK_SPACING}px; }}
QCheckBox:focus {{ color: {AMBER_HEX}; }}
QPushButton:disabled, QPushButton#primary:disabled {{ background: rgba(255,255,255,6); color: {DISABLED_HEX};
    border: 1px solid rgba(255,255,255,16); font-weight: normal; }}
QPushButton#link {{ background: transparent; border: none; color: {AMBER_HEX}; padding: 2px 0; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QLabel#muted {{ color: {MUTED_HEX}; font-size: 12px; }}
QLabel#error {{ color: {ERROR_HEX}; }}
QCheckBox::indicator {{ width: {CHECK_SIZE}px; height: {CHECK_SIZE}px; border: 1px solid rgba(255,255,255,90);
    border-radius: 4px; background: rgba(255,255,255,10); }}
QCheckBox::indicator:checked {{ background: {AMBER_HEX}; border-color: {AMBER_HEX}; image: url({CHECK_ICON}); }}
QCheckBox::indicator:checked:disabled {{ background: rgba(255,178,36,90); }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,60); border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QListWidget::item {{ padding: 6px 4px; }}
QListWidget::item:selected {{ background: rgba(255,255,255,22); color: {TEXT_HEX}; }}
"""

FLOATING = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool


log = logging.getLogger(__name__)

# NSWindowCollectionBehavior flags: on every Space (desktop), over full-screen apps too (a full-screen
# PDF or lecture is where you most want the orb), and left out of Cmd+` window cycling.
CAN_JOIN_ALL_SPACES, MOVE_TO_ACTIVE_SPACE, IGNORES_CYCLE, FULL_SCREEN_AUXILIARY = 1 << 0, 1 << 1, 1 << 6, 1 << 8
EVERYWHERE = CAN_JOIN_ALL_SPACES | FULL_SCREEN_AUXILIARY | IGNORES_CYCLE


def ns_window(w: QWidget):
    """The NSWindow behind a Qt window (macOS only; needs pyobjc, which pynput installs there).

    Only on Qt's Cocoa platform: elsewhere (offscreen, in tests) winId() is not an NSView, and
    handing that pointer to the Objective-C runtime would crash.
    """
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.platformName() != "cocoa":
        return None
    import objc

    return objc.objc_object(c_void_p=int(w.winId())).window()


def join_all_spaces(w: QWidget, find=ns_window) -> bool:
    """Make a floating window follow you to every desktop. Returns False where it can't."""
    if sys.platform != "darwin":
        return False
    try:
        win = find(w)
        if win is None:
            return False
        # Qt marks tool windows MoveToActiveSpace; AppKit refuses that together with CanJoinAllSpaces.
        win.setCollectionBehavior_((int(win.collectionBehavior()) & ~MOVE_TO_ACTIVE_SPACE) | EVERYWHERE)
        return True
    except Exception as exc:  # noqa: BLE001  (no pyobjc, no native window yet)
        log.warning("Could not put %s on every desktop: %s", type(w).__name__, exc)
        return False


class _OnEveryShow(QObject):
    """Qt may recreate the native window when it is shown again; set the behaviour every time."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Show:
            join_all_spaces(obj)
        return False


_ON_SHOW = None


def keep_visible(w: QWidget) -> None:
    """Floating windows stay on screen: when the app loses focus (macOS hides Qt.Tool windows
    then), on every desktop, and over full-screen apps."""
    global _ON_SHOW
    w.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
    if sys.platform == "darwin":
        if _ON_SHOW is None:
            _ON_SHOW = _OnEveryShow()
        w.installEventFilter(_ON_SHOW)


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
