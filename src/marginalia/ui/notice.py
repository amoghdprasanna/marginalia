"""A small window with a message and a row of buttons: crash reports and updates use it."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .theme import DIALOG_STYLE, bring_to_front


class Notice(QWidget):
    """Title, text, buttons. Each button runs its action and closes the window."""

    def __init__(self, title: str, text: str, buttons: list[tuple[str, Callable[[], None] | None]]) -> None:
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Marginalia")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(460)
        self.heading = heading = QLabel(title)
        heading.setStyleSheet("font-size: 15px; font-weight: 600;")
        heading.setWordWrap(True)
        self.text = QLabel(text)
        self.text.setObjectName("muted")
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row = QHBoxLayout()
        row.addStretch(1)
        self.buttons: dict[str, QPushButton] = {}
        for i, (label, action) in enumerate(buttons):
            b = QPushButton(label)
            if i == len(buttons) - 1:
                b.setObjectName("primary")
                b.setDefault(True)
            b.clicked.connect(lambda _=False, a=action: self._run(a))
            row.addWidget(b)
            self.buttons[label] = b
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(heading)
        lay.addWidget(self.text)
        lay.addLayout(row)

    def _run(self, action) -> None:
        self.close()
        if action is not None:
            action()

    def open(self) -> None:
        self.adjustSize()
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        bring_to_front(self)
