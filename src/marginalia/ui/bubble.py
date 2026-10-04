"""The answer bubble: thinking dots, streamed and final answers, copy, follow-ups."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPainter, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .paint import draw_qubit
from .theme import (
    AMBER,
    AMBER_HEX,
    MUTED_HEX,
    TEXT,
    TEXT_HEX,
)
from .widgets import IconButton, Panel, line_edit, muted


class AnswerBubble(Panel):
    closed = Signal()
    followup = Signal(str)
    voice_followup = Signal()

    MAX_BODY = 400

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(440)
        self._drag: QPoint | None = None
        self._markdown = ""

        self.title = muted("", 12)
        self.title.setStyleSheet(f"color: {MUTED_HEX}; font-size: 12px; font-weight: 600; background: transparent;")
        self.close_btn = QToolButton()
        self.close_btn.setText("\u2715")
        self.close_btn.setToolTip("Close (Esc). Ends this thread.")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(
            f"QToolButton {{ color: {MUTED_HEX}; background: transparent; border: none;"
            " font-size: 13px; padding: 2px 4px; }"
            f"QToolButton:hover {{ color: {TEXT_HEX}; }}"
        )
        self.close_btn.clicked.connect(self.dismiss)

        self.status = QLabel()
        self.status.setStyleSheet(f"color: {TEXT_HEX}; font-size: 14px; background: transparent;")
        self._dots = 0
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

        self.meta = muted("", 11)
        self.copy_btn = QToolButton()
        self.copy_btn.setText("Copy")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setStyleSheet(
            f"QToolButton {{ color: {MUTED_HEX}; background: transparent; border: none; font-size: 11px; }}"
            f"QToolButton:hover {{ color: {AMBER_HEX}; }}"
        )
        self.copy_btn.clicked.connect(self._copy)

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
        head.addSpacing(20)  # room for the painted qubit mark
        head.addWidget(self.title, 1)
        head.addWidget(self.close_btn)
        foot = QHBoxLayout()
        foot.addWidget(self.meta, 1)
        foot.addWidget(self.copy_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 14, 14)
        lay.setSpacing(8)
        lay.addLayout(head)
        lay.addWidget(self.status)
        lay.addWidget(self.body)
        lay.addLayout(foot)
        lay.addWidget(self.follow_wrap)

    # states ---------------------------------------------------------------------------------

    def set_voice_available(self, ok: bool) -> None:
        self.follow_mic.setVisible(ok)

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        p = QPainter(self)
        draw_qubit(p, QPointF(25, 21), 6.5, 0.9, halo=False)

    def _set_title(self, question: str) -> None:
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(question, Qt.ElideRight, self.width() - 100))
        self.title.setToolTip(question)

    def show_thinking(self, question: str) -> None:
        self._set_title(question)
        self.body.hide()
        self.meta.hide()
        self.copy_btn.hide()
        self.follow_wrap.hide()
        self.status.show()
        self._dots = 0
        self._tick_dots()
        self._dot_timer.start()
        self.adjustSize()

    def _show_body(self, question: str, markdown: str) -> None:
        self._dot_timer.stop()
        self._set_title(question)
        self._markdown = markdown
        self.status.hide()
        self.body.setMarkdown(markdown)
        self._space_paragraphs()
        self.body.show()
        self.meta.show()

    def show_partial(self, question: str, markdown: str) -> None:
        """The answer so far, while it streams. No copy or follow-up until it is complete."""
        self._show_body(question, markdown)
        self.meta.setText("Writing…")
        self.copy_btn.hide()
        self.follow_wrap.hide()
        self._fit()
        bar = self.body.verticalScrollBar()  # once it outgrows the bubble, follow the newest words
        bar.setValue(bar.maximum())

    def show_answer(self, question: str, markdown: str, meta: str) -> None:
        self._show_body(question, markdown)
        self.meta.setText(meta)
        self.copy_btn.setText("Copy")
        self.copy_btn.show()
        self.follow.clear()
        self.follow_wrap.show()
        self._fit()
        self.body.verticalScrollBar().setValue(0)  # finished: read from the top

    def show_error(self, question: str, message: str) -> None:
        self.show_answer(question, message, "Nothing was sent to the log.")
        self.copy_btn.hide()

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
        self.status.setText("Reading your screen" + "." * self._dots)

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
