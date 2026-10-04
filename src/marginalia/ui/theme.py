"""Colours, window flags and the platform tricks that keep floating windows on top."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
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
