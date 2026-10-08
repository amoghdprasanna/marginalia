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
ERROR_HEX = "#FF8A80"  # only for "this went wrong"; amber stays the colour of the answer's markers

# Ordinary windows (Settings, Setup, Journal): the same slate and amber, with native layout.
DIALOG_STYLE = f"""
QWidget {{ background: {SLATE_HEX}; color: {TEXT_HEX}; font-size: 13px; }}
QGroupBox {{ border: 1px solid rgba(255,255,255,30); border-radius: 10px; margin-top: 14px;
    padding: 12px 10px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {MUTED_HEX}; font-weight: 600; }}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget, QTextBrowser {{
    background: rgba(255,255,255,12); border: 1px solid rgba(255,255,255,30); border-radius: 7px;
    padding: 5px 8px; selection-background-color: {AMBER_HEX}; selection-color: {SLATE_HEX}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {AMBER_HEX}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QCheckBox:disabled,
QPlainTextEdit:disabled {{ color: {MUTED_HEX}; }}
QComboBox QAbstractItemView {{ background: {SLATE_HEX}; selection-background-color: rgba(255,178,36,60); }}
QPushButton {{ background: rgba(255,255,255,16); border: 1px solid rgba(255,255,255,30); border-radius: 7px;
    padding: 6px 14px; }}
QPushButton:hover {{ border-color: {AMBER_HEX}; }}
QPushButton:disabled {{ color: {MUTED_HEX}; }}
QPushButton#primary {{ background: {AMBER_HEX}; color: {SLATE_HEX}; border: none; font-weight: 600; }}
QLabel#muted {{ color: {MUTED_HEX}; font-size: 12px; }}
QLabel#error {{ color: {ERROR_HEX}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid rgba(255,255,255,90); border-radius: 4px;
    background: rgba(255,255,255,10); }}
QCheckBox::indicator:checked {{ background: {AMBER_HEX}; border-color: {AMBER_HEX}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,60); border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QListWidget::item {{ padding: 6px 4px; }}
QListWidget::item:selected {{ background: rgba(255,178,36,50); color: {TEXT_HEX}; }}
"""

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
