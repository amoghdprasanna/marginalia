"""The journal browser: search past questions, reopen a thread with its screenshot, ask more.

It reads the journal itself (read-only data, no Qt in journal.py) but never calls the model:
a follow-up is emitted, and the controller answers it about the saved screenshot (ADR 0019).
"""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPainter, QPixmap, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..journal import Entry, Journal, Thread, to_image_px
from .paint import draw_qubit
from .theme import DIALOG_STYLE, bring_to_front


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgb = img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())  # copy: QImage doesn't own `data`


class ShotView(QWidget):
    """The saved screenshot, scaled to fit, with markers where the latest answer pointed."""

    opened = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.pixmap: QPixmap | None = None
        self.points: list[tuple[float, float, str]] = []  # image px
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Double-click to open the full screenshot")

    def show_image(self, img: Image.Image | None, points: list[tuple[float, float, str]]) -> None:
        self.pixmap = pil_to_pixmap(img) if img is not None else None
        self.points = points
        self.update()

    def image_rect(self) -> QRectF:
        if self.pixmap is None:
            return QRectF()
        pw, ph = self.pixmap.width(), self.pixmap.height()
        k = min(self.width() / pw, self.height() / ph)
        w, h = pw * k, ph * k
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.pixmap is None:
            p.setPen(Qt.gray)
            p.drawText(self.rect(), Qt.AlignCenter, "Screenshot not found")
            return
        r = self.image_rect()
        p.drawPixmap(r, self.pixmap, QRectF(self.pixmap.rect()))
        k = r.width() / self.pixmap.width()
        for x, y, _label in self.points:
            draw_qubit(p, QPointF(r.x() + x * k, r.y() + y * k), 9, 0.9)

    def mouseDoubleClickEvent(self, _e) -> None:  # noqa: N802
        self.opened.emit()


def conversation_markdown(thread: Thread) -> str:
    parts = []
    for e in thread.entries:
        parts.append(f"**{e.question}**\n\n{e.answer}\n\n<sub>{e.when:%d %b %Y, %H:%M} · {e.model}</sub>")
    return "\n\n---\n\n".join(parts)


def set_markdown(view: QTextBrowser, markdown: str) -> None:
    """Markdown with room between paragraphs (Qt's default runs them together)."""
    view.setMarkdown(markdown)
    cur = QTextCursor(view.document())
    cur.select(QTextCursor.Document)
    fmt = QTextBlockFormat()
    fmt.setBottomMargin(7)
    cur.mergeBlockFormat(fmt)
    view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())


class JournalWindow(QWidget):
    followup = Signal(str, str)  # thread id, question

    def __init__(self, journal: Journal) -> None:
        super().__init__(None, Qt.Window)
        self.journal = journal
        self.setWindowTitle("Marginalia Journal")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(980, 640)
        self.thread: Thread | None = None
        self._busy = False

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search questions and answers")
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(self._debounce.start)
        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.currentItemChanged.connect(self._on_select)
        self.count = QLabel()
        self.count.setObjectName("muted")
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.search)
        ll.addWidget(self.list, 1)
        ll.addWidget(self.count)

        self.shot = ShotView()
        self.shot.opened.connect(self._open_shot)
        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(True)
        self.status = QLabel()
        self.status.setObjectName("muted")
        self.ask = QLineEdit()
        self.ask.setPlaceholderText("Ask more about this screenshot")
        self.ask.returnPressed.connect(self._send)
        self.send = QPushButton("Ask")
        self.send.setObjectName("primary")
        self.send.clicked.connect(self._send)
        row = QHBoxLayout()
        row.addWidget(self.ask, 1)
        row.addWidget(self.send)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.shot, 3)
        rl.addWidget(self.body, 4)
        rl.addWidget(self.status)
        rl.addLayout(row)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([300, 680])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.addWidget(split)
        self._set_enabled(False)

    # listing ----------------------------------------------------------------------------------

    def refresh(self, select: str | None = None) -> None:
        keep = select or (self.thread.id if self.thread else None)
        threads = self.journal.threads(self.search.text())
        self.list.blockSignals(True)
        self.list.clear()
        for t in threads:
            turns = f"  ·  {len(t.entries)} questions" if len(t.entries) > 1 else ""
            item = QListWidgetItem(f"{t.first.question}\n{t.last.when:%d %b %Y, %H:%M}{turns}")
            item.setData(Qt.UserRole, t)
            item.setToolTip(t.first.question)
            self.list.addItem(item)
        self.list.blockSignals(False)
        total = len(self.journal.threads())
        self.count.setText(f"{len(threads)} of {total} threads" if self.search.text().strip() else f"{total} threads")
        rows = [i for i in range(self.list.count()) if self.list.item(i).data(Qt.UserRole).id == keep]
        if rows:
            self.list.setCurrentRow(rows[0])
        elif self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.show_thread(None)

    def _on_select(self, item, _prev) -> None:
        self.show_thread(item.data(Qt.UserRole) if item is not None else None)

    def show_thread(self, thread: Thread | None) -> None:
        self.thread = thread
        if thread is None:
            self.shot.show_image(None, [])
            self.body.setMarkdown("Nothing here yet." if not self.search.text() else "No thread matches.")
            self._set_enabled(False)
            return
        last = thread.last
        img = self.journal.image(last)
        points = []
        if img is not None:
            points = [(*to_image_px(last, img.size, x, y), label) for x, y, label in last.points]
        self.shot.show_image(img, points)
        set_markdown(self.body, conversation_markdown(thread))
        self.status.setText("")
        self._set_enabled(img is not None and not self._busy)

    # asking -----------------------------------------------------------------------------------

    def _set_enabled(self, on: bool) -> None:
        self.ask.setEnabled(on)
        self.send.setEnabled(on)

    def _send(self) -> None:
        q = self.ask.text().strip()
        if q and self.thread is not None and not self._busy:
            self.followup.emit(self.thread.id, q)

    def show_thinking(self, question: str) -> None:
        self._busy = True
        self._set_enabled(False)
        self.status.setText(f"Reading the saved screen for “{question}”…")

    def show_partial(self, question: str, text: str) -> None:
        if self.thread is None:
            return
        set_markdown(self.body, conversation_markdown(self.thread) + f"\n\n---\n\n**{question}**\n\n{text}")
        self.status.setText("Writing…")

    def show_answer(self, entry: Entry) -> None:
        self._busy = False
        self.ask.clear()
        self.refresh(select=entry.thread_id)

    def show_error(self, message: str) -> None:
        self._busy = False
        self.status.setText(message)
        self._set_enabled(self.thread is not None)

    def _open_shot(self) -> None:
        if self.thread is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.journal.dir / self.thread.last.shot)))

    def open(self) -> None:
        self.journal.backfill()
        self.refresh()
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        bring_to_front(self)
