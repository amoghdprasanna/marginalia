"""The answer bubble: working, streamed and final answers, errors you can act on, follow-ups.

Design notes (docs/design.md): the bubble always says what is happening (working, writing,
done, failed) and what you can do next; an error offers its fix as a button; details meant
for debugging live in tooltips, not in the text you read.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .paint import draw_qubit
from .theme import AMBER, AMBER_HEX, ERROR_HEX, MUTED_HEX, SLATE_HEX, TEXT, TEXT_HEX
from .widgets import IconButton, Panel, line_edit, muted

LINK_STYLE = (
    f"QToolButton {{ color: {MUTED_HEX}; background: transparent; border: none; font-size: 12px;"
    " padding: 3px 6px; border-radius: 6px; }"
    f"QToolButton:hover {{ color: {AMBER_HEX}; background: rgba(255,255,255,12); }}"
)
ACTION_STYLE = (
    "QPushButton { color: %s; background: rgba(255,255,255,16); border: 1px solid rgba(255,255,255,30);"
    " border-radius: 8px; padding: 6px 14px; font-size: 13px; }"
    f"QPushButton:hover {{ border-color: {AMBER_HEX}; }}"
    f"QPushButton#primary {{ color: {SLATE_HEX}; background: {AMBER_HEX}; border: none; font-weight: 600; }}"
) % TEXT_HEX

SLOW_S = 3  # after this long, show the seconds ticking so a slow answer doesn't look stuck


def link_button(text: str, tip: str = "") -> QToolButton:
    b = QToolButton()
    b.setText(text)
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(LINK_STYLE)
    return b


class AnswerBubble(Panel):
    closed = Signal()
    followup = Signal(str)
    voice_followup = Signal()
    replay_requested = Signal()  # fly the markers again

    MAX_BODY = 400

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(440)
        self._drag: QPoint | None = None
        self._markdown = ""
        self._failed = False

        self.title = muted("", 12)
        self.title.setStyleSheet(f"color: {MUTED_HEX}; font-size: 12px; font-weight: 600; background: transparent;")
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setToolTip("Close (Esc). Ends this conversation.")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFixedSize(26, 26)  # a target you can hit without aiming
        self.close_btn.setStyleSheet(
            f"QToolButton {{ color: {MUTED_HEX}; background: transparent; border: none; font-size: 13px;"
            " border-radius: 13px; }"
            f"QToolButton:hover {{ color: {TEXT_HEX}; background: rgba(255,255,255,20); }}"
        )
        self.close_btn.clicked.connect(self.dismiss)

        self.status = QLabel()
        self.status.setStyleSheet(f"color: {TEXT_HEX}; font-size: 14px; background: transparent;")
        self._dots = 0
        self._clock = QElapsedTimer()
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(380)
        self._dot_timer.timeout.connect(self._tick_dots)

        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(True)
        self.body.setFrameShape(QTextBrowser.NoFrame)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body.setStyleSheet(
            f"QTextBrowser {{ background: transparent; border: none; color: {TEXT_HEX}; font-size: 14px; }}"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,60); border-radius: 4px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        pal = self.body.palette()
        pal.setColor(QPalette.Link, AMBER)
        pal.setColor(QPalette.Text, TEXT)
        self.body.setPalette(pal)

        # The footer: what happened (left), what you can do with it (right).
        self.meta = muted("", 12)
        self.replay_btn = link_button("", "Fly the markers to these places again")
        self.replay_btn.clicked.connect(self.replay_requested.emit)
        self.copy_btn = link_button("Copy", "Copy the answer as Markdown")
        self.copy_btn.clicked.connect(self._copy)
        self.stop_btn = link_button("Stop", "Stop this answer (Esc)")
        self.stop_btn.clicked.connect(self.dismiss)

        # An error's way out, as buttons ("Try again", "Open Settings").
        self.actions = QWidget()
        self.actions.setStyleSheet(ACTION_STYLE)
        self._actions_lay = QHBoxLayout(self.actions)
        self._actions_lay.setContentsMargins(0, 2, 0, 0)
        self._actions_lay.setSpacing(8)
        self.action_buttons: dict[str, QPushButton] = {}

        self.follow = line_edit("Ask a follow-up", 13)
        self.follow.returnPressed.connect(self._followup)
        self.follow_mic = IconButton("mic", "Ask the follow-up by voice", 26)
        self.follow_mic.clicked.connect(self.voice_followup.emit)
        self.follow_send = IconButton("send", "Send (Enter)", 26)
        self.follow_send.filled = True
        self.follow_send.clicked.connect(self._followup)
        self.follow_send.setEnabled(False)
        self.follow.textChanged.connect(lambda t: self.follow_send.setEnabled(bool(t.strip())))
        self.follow_wrap = QWidget()
        self.follow_wrap.setObjectName("followWrap")
        self.follow_wrap.setAttribute(Qt.WA_StyledBackground)
        self.follow_wrap.setStyleSheet(
            "#followWrap { background: rgba(255,255,255,14); border: 1px solid rgba(255,255,255,22);"
            " border-radius: 10px; }"
        )
        fl = QHBoxLayout(self.follow_wrap)
        fl.setContentsMargins(12, 4, 4, 4)
        fl.setSpacing(2)
        fl.addWidget(self.follow, 1)
        fl.addWidget(self.follow_mic)
        fl.addWidget(self.follow_send)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addSpacing(20)  # room for the painted mark
        head.addWidget(self.title, 1)
        head.addWidget(self.close_btn)
        self.footer = QWidget()
        foot = QHBoxLayout(self.footer)
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(2)
        foot.addWidget(self.meta, 1)
        foot.addWidget(self.replay_btn)
        foot.addWidget(self.copy_btn)
        foot.addWidget(self.stop_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 10, 12, 14)
        lay.setSpacing(8)
        lay.addLayout(head)
        lay.addWidget(self.status)
        lay.addWidget(self.body)
        lay.addWidget(self.actions)
        lay.addWidget(self.footer)
        lay.addWidget(self.follow_wrap)

    # states ---------------------------------------------------------------------------------

    def set_voice_available(self, ok: bool) -> None:
        self.follow_mic.setVisible(ok)

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(25, 23)
        if not self._failed:
            draw_qubit(p, c, 6.5, 0.9, halo=False)
            return
        p.setPen(Qt.NoPen)  # an error: a filled mark with "!", the one place this colour appears
        p.setBrush(QColor(ERROR_HEX))
        p.drawEllipse(c, 8, 8)
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QPen(QColor(SLATE_HEX)))
        p.drawText(QRectF(c.x() - 8, c.y() - 8, 16, 16), Qt.AlignCenter, "!")

    def _set_title(self, question: str) -> None:
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(question, Qt.ElideRight, self.width() - 100))
        self.title.setToolTip(question)

    def _set_footer(self, *, meta: bool, replay: bool = False, copy: bool = False, stop: bool = False) -> None:
        if not meta:
            self.meta.setText("")  # stays, empty, to keep the buttons on the right
        self.replay_btn.setVisible(replay)
        self.copy_btn.setVisible(copy)
        self.stop_btn.setVisible(stop)
        self.footer.setVisible(meta or replay or copy or stop)

    def _set_actions(self, actions: list[tuple[str, Callable[[], None]]]) -> None:
        while self._actions_lay.count():
            item = self._actions_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.action_buttons = {}
        for i, (label, fn) in enumerate(actions):
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            if i == 0:
                b.setObjectName("primary")  # the likeliest fix goes first and stands out
            b.clicked.connect(lambda _=False, f=fn: f())
            self._actions_lay.addWidget(b)
            self.action_buttons[label] = b
        self._actions_lay.addStretch(1)
        self.actions.setVisible(bool(actions))

    def show_thinking(self, question: str) -> None:
        self._failed = False
        self._set_title(question)
        self.body.hide()
        self._set_actions([])
        self.follow_wrap.hide()
        self.status.show()
        self.meta.setText("")
        self.meta.setToolTip("")
        self._set_footer(meta=False, stop=True)
        self._dots = 0
        self._clock.restart()
        self._tick_dots()
        self._dot_timer.start()
        self.adjustSize()
        self.update()

    def _show_body(self, question: str, markdown: str) -> None:
        self._dot_timer.stop()
        self._set_title(question)
        self._markdown = markdown
        self.status.hide()
        self.body.setMarkdown(markdown)
        self._space_paragraphs()
        self.body.show()

    def show_partial(self, question: str, markdown: str) -> None:
        """The answer so far, while it streams. Copy and follow-ups wait until it is complete."""
        self._show_body(question, markdown)
        self.meta.setText("Writing…")
        self._set_footer(meta=True, stop=True)
        self.follow_wrap.hide()
        self._fit()
        bar = self.body.verticalScrollBar()  # once it outgrows the bubble, follow the newest words
        bar.setValue(bar.maximum())

    def show_answer(self, question: str, markdown: str, meta: str, details: str = "", points: int = 0) -> None:
        """The finished answer. `meta` is the short footer; `details` its tooltip; `points` the markers shown."""
        self._failed = False
        self._show_body(question, markdown)
        self._set_actions([])
        self.meta.setText(meta)
        self.meta.setToolTip(details)
        if points:
            self.replay_btn.setText("Show again" if points == 1 else f"Show {points} places again")
        self._set_footer(meta=True, replay=bool(points), copy=True)
        self.copy_btn.setText("Copy")
        self.follow.clear()
        self.follow_wrap.show()
        self._fit()
        self.body.verticalScrollBar().setValue(0)  # finished: read from the top
        self.update()

    def show_error(
        self, question: str, message: str, actions: list[tuple[str, Callable[[], None]]] | tuple = ()
    ) -> None:
        """Something went wrong. With `actions`, offer them; without, you can rephrase below."""
        self._failed = True
        self._show_body(question, message)
        self.meta.setText("")
        self.meta.setToolTip("")
        self._set_footer(meta=False)
        self._set_actions(list(actions))
        self.follow.clear()
        self.follow_wrap.setVisible(not actions)
        self._fit()
        self.update()

    def _space_paragraphs(self) -> None:
        from PySide6.QtGui import QTextBlockFormat, QTextCursor

        cur = QTextCursor(self.body.document())
        cur.select(QTextCursor.Document)
        fmt = QTextBlockFormat()
        fmt.setBottomMargin(7)
        fmt.setLineHeight(118, 1)  # 1 = ProportionalHeight
        cur.mergeBlockFormat(fmt)

    def _fit(self) -> None:
        doc = self.body.document()
        doc.setTextWidth(self.width() - 32 - 2 * doc.documentMargin())
        h = int(doc.size().height()) + 8
        self.body.setFixedHeight(max(28, min(h, self.MAX_BODY)))
        self.adjustSize()

    def _tick_dots(self) -> None:
        self._dots = (self._dots % 3) + 1
        seconds = self._clock.elapsed() // 1000
        if seconds < SLOW_S:
            self.status.setText("Reading your screen" + "." * self._dots)
        else:
            self.status.setText(f"Thinking{'.' * self._dots}  {seconds} s")

    # actions --------------------------------------------------------------------------------

    def dismiss(self) -> None:
        self._dot_timer.stop()
        self.hide()
        self.closed.emit()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._markdown)
        self.copy_btn.setText("Copied")
        QTimer.singleShot(1200, self, lambda: self.copy_btn.setText("Copy"))

    def _followup(self) -> None:
        q = self.follow.text().strip()
        if q:
            self.followup.emit(q)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(e)

    # drag by the header ----------------------------------------------------------------------

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton and e.position().y() < 40:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802
        self._drag = None
