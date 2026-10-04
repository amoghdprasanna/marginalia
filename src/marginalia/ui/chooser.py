"""Pops out of the orb on click: ask by typing or by voice."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
)

from .theme import (
    MUTED_HEX,
    bring_to_front,
)
from .widgets import Chip, Panel, muted


class ModeChooser(Panel):
    """Pops out of the orb on click: ask by typing or by voice."""

    chosen = Signal(str)  # "type" or "voice"

    def __init__(self) -> None:
        super().__init__()
        self.radius = 14
        self.label = muted("Ask about the screen", 11)
        self.label.setStyleSheet(f"color: {MUTED_HEX}; font-size: 11px; font-weight: 600; background: transparent;")
        self.type_btn = Chip("keys", "Type", "T")
        self.voice_btn = Chip("mic", "Speak", "V")
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
