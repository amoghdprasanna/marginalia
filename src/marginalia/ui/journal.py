"""The journal browser: search past questions, reopen a thread with its screenshot, ask more.

It reads the journal itself (read-only data, no Qt in journal.py) but never calls the model:
a follow-up is emitted, and the controller answers it about the saved screenshot (ADR 0019).
"""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QFont,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
    QTextBlockFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..journal import Entry, Journal, Thread, to_image_px
from ..providers import model_name
from .paint import draw_qubit
from .theme import DIALOG_STYLE, FILL_HOVER, FILL_SELECTED, MUTED, MUTED_HEX, TEXT, bring_to_front, tint


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
        self.missing = ""  # what to say where the picture would be
        self.empty = False  # no thread at all: `missing` is the window's message, title then text
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Double-click to open the full screenshot")

    def show_image(
        self, img: Image.Image | None, points: list[tuple[float, float, str]], missing: str = "Screenshot not found"
    ) -> None:
        self.pixmap = pil_to_pixmap(img) if img is not None else None
        self.points = points
        self.missing = missing
        self.empty = False
        self.setCursor(Qt.PointingHandCursor if img is not None else Qt.ArrowCursor)
        self.setToolTip("Double-click to open the full screenshot" if img is not None else "")
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
        if self.pixmap is None and self.empty:  # the whole window's empty state: the mark, then what to do
            p.setRenderHint(QPainter.Antialiasing)
            title, _, more = self.missing.partition("\n")
            top = self.height() / 2 - 70
            draw_qubit(p, QPointF(self.width() / 2, top), 20, 0.9, halo=False)
            box = QRectF((self.width() - 420) / 2, top + 40, 420, 200)
            f = QFont(self.font())
            f.setPixelSize(16)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(TEXT)
            p.drawText(box, Qt.AlignHCenter | Qt.AlignTop, title)
            f.setPixelSize(13)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(MUTED)
            p.drawText(box.adjusted(0, 30, 0, 0), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, more)
            return
        if self.pixmap is None:
            p.setPen(MUTED)
            p.drawText(self.rect(), Qt.AlignCenter, self.missing)
            return
        r = self.image_rect()
        p.drawPixmap(r, self.pixmap, QRectF(self.pixmap.rect()))
        k = r.width() / self.pixmap.width()
        for x, y, _label in self.points:
            draw_qubit(p, QPointF(r.x() + x * k, r.y() + y * k), 9, 0.9)

    def mouseDoubleClickEvent(self, _e) -> None:  # noqa: N802
        self.opened.emit()


def conversation_markdown(thread: Thread, shown: bool = False) -> str:
    """The thread as Markdown: to copy, or (`shown`) to read in the window, where each answer's
    date and model are a quiet line in words ("Claude Opus 5.5", not its id)."""
    parts = []
    for e in thread.entries:
        if shown:
            when = f"{e.when:%d %b %Y, %H:%M} · {model_name(e.model)}"
            meta = f"<span style='color:{MUTED_HEX}; font-size:12px'>{when}</span>"
        else:
            meta = f"<sub>{e.when:%d %b %Y, %H:%M} · {e.model}</sub>"
        parts.append(f"**{e.question}**\n\n{e.answer}\n\n{meta}")
    return "\n\n---\n\n".join(parts)


class ThreadDelegate(QStyledItemDelegate):
    """A thread in the list: its first question, then a quieter line with when and how long."""

    PAD = 10

    def sizeHint(self, option, index):  # noqa: N802
        return QSize(option.rect.width(), 2 * option.fontMetrics.height() + 2 * self.PAD + 2)

    def paint(self, p: QPainter, option, index) -> None:
        title, _, meta = index.data(Qt.DisplayRole).partition("\n")
        r = option.rect.adjusted(4, 2, -4, -2)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if option.state & QStyle.State_Selected:
            p.setPen(Qt.NoPen)
            p.setBrush(tint("#FFFFFF", FILL_SELECTED))
            p.drawRoundedRect(r, 6, 6)
        elif option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(tint("#FFFFFF", FILL_HOVER))
            p.drawRoundedRect(r, 6, 6)
        text = r.adjusted(self.PAD, self.PAD - 1, -self.PAD, -self.PAD)
        f = QFont(option.font)
        f.setWeight(QFont.DemiBold if option.state & QStyle.State_Selected else QFont.Normal)
        p.setFont(f)
        p.setPen(TEXT)
        line = p.fontMetrics().height()
        p.drawText(text.adjusted(0, 0, 0, -line), Qt.AlignLeft | Qt.AlignTop,
                   p.fontMetrics().elidedText(title, Qt.ElideRight, text.width()))  # fmt: skip
        small = QFont(option.font)
        small.setPixelSize(12)
        p.setFont(small)
        p.setPen(MUTED)
        p.drawText(text.adjusted(0, line + 1, 0, 0), Qt.AlignLeft | Qt.AlignTop, meta)
        p.restore()


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
        find = QKeySequence(QKeySequence.Find)
        self.search.setPlaceholderText(f"Search questions and answers  ({find.toString(QKeySequence.NativeText)})")
        QShortcut(find, self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(self._debounce.start)
        self.list = QListWidget()
        self.list.setItemDelegate(ThreadDelegate(self.list))
        self.list.setMouseTracking(True)  # hover highlight
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.currentItemChanged.connect(self._on_select)
        self.count = QLabel()
        self.count.setObjectName("muted")
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 6, 0)
        ll.addWidget(self.search)
        ll.addWidget(self.list, 1)
        ll.addWidget(self.count)

        self.shot = ShotView()
        self.shot.opened.connect(self._open_shot)
        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(True)
        self.status = QLabel()
        self.status.setObjectName("muted")
        self.status.hide()  # shown only with something to say, so it leaves no gap
        self.ask = QLineEdit()
        self.ask.setPlaceholderText("Ask more about this screenshot (Enter)")
        self.ask.returnPressed.connect(self._send)
        self.send = QPushButton("Ask")
        self.send.setObjectName("primary")
        self.send.clicked.connect(self._send)
        # Ctrl means Cmd on macOS.
        copy_keys = QKeySequence("Ctrl+Shift+C")
        self.copy = QPushButton("Copy")
        self.copy.setToolTip(f"Copy this thread as Markdown  ({copy_keys.toString(QKeySequence.NativeText)})")
        self.copy.clicked.connect(self._copy)
        QShortcut(copy_keys, self, activated=self._copy)
        row = QHBoxLayout()
        row.addWidget(self.ask, 1)
        row.addWidget(self.send)
        row.addWidget(self.copy)
        self.ask_row = QWidget()
        self.ask_row.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        rl.addWidget(self.shot, 3)
        rl.addWidget(self.body, 4)
        rl.addWidget(self.status)
        rl.addWidget(self.ask_row)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([300, 680])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.addWidget(split)
        self._set_enabled(False)
        self.copy.setEnabled(False)

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
        noun = "thread" if total == 1 else "threads"
        self.count.setText(f"{len(threads)} of {total} {noun}" if self.search.text().strip() else f"{total} {noun}")
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
        # Nothing to show: no conversation box, no box to ask in, no buttons; one message, centred.
        self.ask_row.setVisible(thread is not None)
        self.body.setVisible(thread is not None)
        if thread is None:
            query = self.search.text().strip()
            # An empty view says why it's empty and what to do about it.
            message = (
                f"Nothing mentions “{query}”\nTry fewer or different words."
                if query
                else "Nothing here yet.\nClick the orb and ask about something on your screen. Every question "
                "and answer lands here with its screenshot, so you can find it and ask more later."
            )
            self.shot.show_image(None, [], missing=message)
            self.shot.empty = True
            self.shot.update()
            self.body.setPlainText(message)  # what a screen reader reads
            self._set_enabled(False)
            self.copy.setEnabled(False)
            return
        last = thread.last
        img = self.journal.image(last)
        points = []
        if img is not None:
            points = [(*to_image_px(last, img.size, x, y), label) for x, y, label in last.points]
        self.shot.show_image(img, points)
        set_markdown(self.body, conversation_markdown(thread, shown=True))
        self._say("")
        self._set_enabled(img is not None and not self._busy)
        self.copy.setEnabled(True)

    def _say(self, text: str) -> None:
        self.status.setText(text)
        self.status.setVisible(bool(text))

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
        self._say(f"Reading the saved screen for “{question}”…")

    def show_partial(self, question: str, text: str) -> None:
        if self.thread is None:
            return
        set_markdown(self.body, conversation_markdown(self.thread, shown=True) + f"\n\n---\n\n**{question}**\n\n{text}")
        self._say("Writing…")

    def show_answer(self, entry: Entry) -> None:
        self._busy = False
        self.ask.clear()
        self.refresh(select=entry.thread_id)

    def show_error(self, message: str) -> None:
        self._busy = False
        self._say(message)
        self._set_enabled(self.thread is not None)

    def _copy(self) -> None:
        if self.thread is None:
            return
        QGuiApplication.clipboard().setText(conversation_markdown(self.thread))
        n = len(self.thread.entries)
        self._say(f"Copied {n} question{'s' if n != 1 else ''} as Markdown")

    def _open_shot(self) -> None:
        if self.thread is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.journal.dir / self.thread.last.shot)))

    def open(self) -> None:
        self.journal.backfill()
        self.refresh()
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        bring_to_front(self)
