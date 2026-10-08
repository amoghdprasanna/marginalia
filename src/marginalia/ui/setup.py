"""The setup check: what Marginalia needs from the system, and a button to fix each thing.

Shown on first run and whenever something required is missing at startup; reopen it from the
orb menu. It only displays checks and emits which one to fix; permissions.Fixer does the rest.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..permissions import MISSING, OFF, OK, Check
from .theme import AMBER, DIALOG_STYLE, MUTED_HEX, bring_to_front

COLORS = {OK: QColor(110, 204, 140), MISSING: AMBER, OFF: QColor(MUTED_HEX)}


class Dot(QWidget):
    def __init__(self, status: str) -> None:
        super().__init__()
        self.status = status
        self.setFixedSize(12, 12)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(COLORS.get(self.status, QColor(MUTED_HEX)))
        p.drawEllipse(1, 1, 10, 10)


class SetupWindow(QWidget):
    fix_requested = Signal(object)  # the Check whose button was pressed
    recheck_requested = Signal()
    restart_requested = Signal()
    done = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.Window)
        self.setWindowTitle("Marginalia Setup")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(560)
        self.title = QLabel("Let's check Marginalia can do its job")
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.intro = QLabel()
        self.intro.setObjectName("muted")
        self.intro.setWordWrap(True)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(12)
        self.recheck = QPushButton("Check again")
        self.restart = QPushButton("Restart Marginalia")
        self.close_btn = QPushButton("Done")
        self.close_btn.setObjectName("primary")
        self.recheck.clicked.connect(self.recheck_requested.emit)
        self.restart.clicked.connect(self.restart_requested.emit)
        self.close_btn.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addWidget(self.recheck)
        buttons.addWidget(self.restart)
        buttons.addStretch(1)
        buttons.addWidget(self.close_btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(self.title)
        lay.addWidget(self.intro)
        lay.addLayout(self.grid)
        lay.addLayout(buttons)
        self.checks: list[Check] = []
        self.buttons: dict[str, QPushButton] = {}

    def show_checks(self, checks: list[Check], host: str) -> None:
        self.checks = checks
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.buttons.clear()
        for row, check in enumerate(checks):
            title = QLabel(check.title)
            title.setStyleSheet("font-weight: 600;")
            detail = QLabel(check.detail)
            detail.setObjectName("muted")
            detail.setWordWrap(True)
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(title)
            text.addWidget(detail)
            holder = QWidget()
            holder.setLayout(text)
            self.grid.addWidget(Dot(check.status), row, 0, Qt.AlignTop | Qt.AlignHCenter)
            self.grid.addWidget(holder, row, 1)
            if check.action and check.status != OK:
                btn = QPushButton(check.action)
                btn.clicked.connect(lambda _=False, c=check: self.fix_requested.emit(c))
                self.buttons[check.key] = btn
                self.grid.addWidget(btn, row, 2, Qt.AlignTop)
        self.grid.setColumnStretch(1, 1)
        self.intro.setText(
            f"macOS asks about {host}, the app Marginalia runs in. After allowing Screen Recording, "
            f"quit and reopen {host}."
            if host != "Marginalia"
            else "After allowing Screen Recording, restart Marginalia."
        )
        # From a terminal, restarting Marginalia doesn't help: the terminal itself must restart.
        self.restart.setVisible(host == "Marginalia" and any(c.key == "screen" and c.status != OK for c in checks))
        self.adjustSize()

    def open(self) -> None:
        self.adjustSize()
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        bring_to_front(self)

    def closeEvent(self, e) -> None:  # noqa: N802
        self.done.emit()
        super().closeEvent(e)
