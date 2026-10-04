"""The box you type a question into."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
)

from .paint import draw_qubit
from .theme import (
    bring_to_front,
)
from .widgets import IconButton, Panel, hints, line_edit


class AskBox(Panel):
    submitted = Signal(str)
    cancelled = Signal()
    voice_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(460)
        self.edit = line_edit("Ask about what's on your screen", 15)
        self.mic = IconButton("mic", "Ask by voice instead")
        self.mic.clicked.connect(self._to_voice)
        self.hint = hints(("Enter", "ask"), ("Esc", "close"))
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
