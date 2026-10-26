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

# Colour tokens (docs/design.md, "Tokens"). tests/ui/test_theme.py checks them against every
# surface: 4.5:1 for text, 3:1 for the edge of a field (WCAG 2.1, 1.4.3 and 1.4.11), and that
# "ready", "needs you" and "went wrong" stay apart for the three kinds of colour blindness.
SLATE_HEX = "#1B2031"  # windows and panels
SIDEBAR_HEX = "#161A28"  # a shade under the slate: the Settings sidebar
RAISED_HEX = "#262C42"  # a shade over it: tooltips, list pop-ups
TEXT_HEX = "#ECEFF7"  # body text, 14:1
TEXT_SOFT_HEX = "#C4CADB"  # the keys in a hint row, between body and muted
MUTED_HEX = "#9BA3BC"  # secondary text and hints, 6.4:1
DISABLED_HEX = "#6B7290"  # can't use it now: fainter than muted, so it never reads as "secondary"
FIELD_EDGE_HEX = "#6B7391"  # the edge of a text field or checkbox, 3:1: you can see where to type
AMBER_HEX = "#FFB224"  # the accent: the answer's markers, the qubit, primary buttons, focus
AMBER_HOVER_HEX = "#FFC452"
AMBER_DOWN_HEX = "#E99A0B"
OK_HEX = "#6EE7B7"  # "ready" (setup check): a mint, not a yellow-green, to stay clear of amber
ERROR_HEX = "#F2735F"  # only for "this went wrong"; a warm red that colour-blind eyes don't take for green

# White laid over the slate, faint to strong: how much (alpha, 0-255) for each use.
FILL_CARD, FILL_HOVER, FILL_FIELD, FILL_BUTTON, FILL_SELECTED, FILL_BUTTON_HOVER = 6, 10, 12, 16, 26, 28
LINE = 24  # dividers and card edges: decoration, so they may stay quiet
EDGE_ALPHA = 34  # the rim of a floating panel


def white(alpha: int) -> str:
    """White at `alpha`, for a style sheet."""
    return f"rgba(255,255,255,{alpha})"


def tint(color: str | QColor, alpha: int) -> QColor:
    """`color` at `alpha`, for painting."""
    c = QColor(color)
    c.setAlpha(alpha)
    return c


SLATE = tint(SLATE_HEX, 246)
PILL = tint(SLATE_HEX, 228)
EDGE = tint("#FFFFFF", EDGE_ALPHA)
TEXT = QColor(TEXT_HEX)
MUTED = QColor(MUTED_HEX)
DISABLED = QColor(DISABLED_HEX)
AMBER = QColor(AMBER_HEX)
HALO = QColor(10, 12, 22, 120)  # under the qubit on a white page

CHECK_SIZE, CHECK_SPACING = 15, 8

ASSETS = Path(__file__).parent / "assets"
CHECK_ICON = (ASSETS / "check.svg").as_posix()
CHEVRON_ICON = (ASSETS / "chevron.svg").as_posix()

# Ordinary windows (Settings, Setup, Journal): the same slate and amber, with native layout.
# Hover lightens, focus draws an amber ring, pressing darkens: three states you can tell apart.
DIALOG_STYLE = f"""
QWidget {{ background: {SLATE_HEX}; color: {TEXT_HEX}; font-size: 13px; }}
QToolTip {{ background: {RAISED_HEX}; color: {TEXT_HEX}; border: 1px solid {white(LINE)}; border-radius: 6px;
    padding: 4px 7px; }}
QFrame#card {{ background: {white(FILL_CARD)}; border: 1px solid {white(LINE)}; border-radius: 10px; }}
QFrame#card QLabel, QFrame#card QCheckBox, QFrame#card QWidget#row {{ background: transparent; }}
QLabel#heading {{ font-size: 17px; font-weight: 600; padding-left: 2px; }}
QWidget#sidebar {{ background: {SIDEBAR_HEX}; border-right: 1px solid {white(LINE)}; }}
QListWidget#nav {{ background: transparent; border: none; padding: 0; outline: 0; }}
QListWidget#nav::item {{ padding: 7px 10px; margin: 1px 0; border-radius: 6px; color: {TEXT_HEX}; }}
QListWidget#nav::item:hover {{ background: {white(FILL_HOVER)}; }}
QListWidget#nav::item:selected {{ background: {white(FILL_SELECTED)}; color: {TEXT_HEX}; font-weight: 600; }}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background: {white(FILL_FIELD)}; border: 1px solid {FIELD_EDGE_HEX}; border-radius: 7px;
    padding: 5px 8px; selection-background-color: {AMBER_HEX}; selection-color: {SLATE_HEX}; }}
QListWidget, QTextBrowser {{ background: {white(FILL_FIELD)}; border: 1px solid {white(LINE)}; border-radius: 7px;
    padding: 5px 8px; selection-background-color: {AMBER_HEX}; selection-color: {SLATE_HEX}; outline: 0; }}
QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {MUTED_HEX}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {AMBER_HEX}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QCheckBox:disabled, QPlainTextEdit:disabled {{
    color: {DISABLED_HEX}; border-color: {white(LINE)}; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 24px;
    border: none; background: transparent; }}
QComboBox::down-arrow {{ image: url({CHEVRON_ICON}); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: none; }}
QComboBox QAbstractItemView {{ background: {RAISED_HEX}; border: 1px solid {white(LINE)}; outline: 0;
    selection-background-color: {white(FILL_SELECTED)}; selection-color: {TEXT_HEX}; }}
QPushButton {{ background: {white(FILL_BUTTON)}; border: 1px solid {white(LINE)}; border-radius: 7px;
    padding: 6px 14px; }}
QPushButton:focus, QPushButton#primary:focus {{ padding: 5px 13px; }}
QPushButton:hover {{ background: {white(FILL_BUTTON_HOVER)}; }}
QPushButton:pressed {{ background: {white(FILL_CARD)}; }}
QPushButton:focus {{ border: 2px solid {AMBER_HEX}; }}
QPushButton#primary {{ background: {AMBER_HEX}; color: {SLATE_HEX}; border: 1px solid {AMBER_HEX}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {AMBER_HOVER_HEX}; }}
QPushButton#primary:pressed {{ background: {AMBER_DOWN_HEX}; }}
QPushButton#primary:focus {{ border: 2px solid {TEXT_HEX}; }}
QPushButton:disabled, QPushButton#primary:disabled {{ background: {white(FILL_CARD)}; color: {DISABLED_HEX};
    border: 1px solid {white(FILL_BUTTON)}; font-weight: normal; }}
QPushButton#link {{ background: transparent; border: none; color: {AMBER_HEX}; padding: 2px 0; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QCheckBox {{ spacing: {CHECK_SPACING}px; background: transparent; }}
QCheckBox:focus {{ color: {AMBER_HEX}; }}
QCheckBox::indicator {{ width: {CHECK_SIZE}px; height: {CHECK_SIZE}px; border: 1px solid {FIELD_EDGE_HEX};
    border-radius: 4px; background: {white(FILL_FIELD)}; }}
QCheckBox::indicator:hover {{ border-color: {MUTED_HEX}; }}
QCheckBox::indicator:checked {{ background: {AMBER_HEX}; border-color: {AMBER_HEX}; image: url({CHECK_ICON}); }}
QCheckBox::indicator:disabled {{ border-color: {white(LINE)}; background: transparent; }}
QCheckBox::indicator:checked:disabled {{ background: {tint(AMBER_HEX, 90).name(QColor.HexArgb)};
    border-color: transparent; }}
QLabel#muted {{ color: {MUTED_HEX}; font-size: 12px; }}
QLabel#error {{ color: {ERROR_HEX}; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {white(60)}; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {white(100)}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QListWidget::item {{ padding: 6px 4px; }}
QListWidget::item:selected {{ background: {white(FILL_SELECTED)}; color: {TEXT_HEX}; }}
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


def fit_height(w: QWidget) -> None:
    """Make a fixed-width window exactly as tall as its content at that width. adjustSize()
    measures word-wrapped text at a width of its own choosing, so such windows came out too tall
    (empty bands between lines) or too short (cut-off text)."""
    lay = w.layout()
    lay.activate()
    w.resize(w.width(), max(lay.totalHeightForWidth(w.width()), lay.totalMinimumSize().height()))


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
