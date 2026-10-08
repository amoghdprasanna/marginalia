"""Overlay windows: the floating orb, the ask box, the answer bubble and the pointer layer.

Visual language: a quiet slate glass for text, and one amber "qubit" mark (a ring with an
equator and a state dot riding it) that is the only thing allowed to move or shout.

Widgets only draw and emit signals; the controller in app.py decides what happens next.
"""
from .askbox import AskBox
from .bubble import AnswerBubble
from .chooser import ModeChooser
from .journal import JournalWindow
from .listen import ListenBox
from .orb import Orb
from .overlay import PointerOverlay
from .paint import draw_icon, draw_qubit
from .settings import SettingsWindow
from .setup import SetupWindow

__all__ = [
    "AnswerBubble",
    "AskBox",
    "JournalWindow",
    "ListenBox",
    "ModeChooser",
    "Orb",
    "PointerOverlay",
    "SettingsWindow",
    "SetupWindow",
    "draw_icon",
    "draw_qubit",
]
