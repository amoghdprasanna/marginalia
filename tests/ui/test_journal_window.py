"""The journal browser: list, search, reopen, and the follow-up box."""

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from marginalia.doubtlog import DoubtLog
from marginalia.journal import Journal
from marginalia.ui import JournalWindow


@pytest.fixture
def window(qtbot, tmp_path):
    log = DoubtLog(tmp_path)
    img = Image.new("RGB", (400, 250), (240, 240, 240))
    log.add("what is the code distance?", "The **minimum** weight of a logical.", img, "m", points=[(10, 10, "d")])
    log.add("why odd?", "Majority vote.", img, "m", thread=log.last_entry.id)
    log.add("what is a stabilizer?", "A Pauli that fixes the code space.", img, "m")
    w = JournalWindow(Journal(tmp_path))
    qtbot.addWidget(w)
    w.refresh()
    return w


def test_lists_threads_newest_first_and_opens_the_first(window):
    assert window.list.count() == 2
    assert window.thread.first.question == "what is a stabilizer?"
    assert "2 threads" in window.count.text()
    assert window.shot.pixmap is not None


def test_selecting_a_thread_shows_the_conversation(window):
    window.list.setCurrentRow(1)
    text = window.body.toPlainText()
    assert "what is the code distance?" in text and "Majority vote." in text
    assert "2 questions" in window.list.item(1).text()


def test_search_filters(qtbot, window):
    window.search.setText("majority")
    qtbot.waitUntil(lambda: window.list.count() == 1)
    assert window.thread.first.question == "what is the code distance?"
    assert "1 of 2" in window.count.text()
    window.search.setText("zzz")
    qtbot.waitUntil(lambda: window.list.count() == 0)
    assert "mentions “zzz”" in window.body.toPlainText() and not window.ask.isEnabled()


def test_asking_emits_the_thread_and_question(qtbot, window):
    window.ask.setText("and for the surface code?")
    with qtbot.waitSignal(window.followup) as sig:
        window._send()
    assert sig.args == [window.thread.id, "and for the surface code?"]


def test_busy_states(window):
    window.show_thinking("q")
    assert not window.ask.isEnabled() and "Reading" in window.status.text()
    window.show_partial("q", "half an ans")
    assert "half an ans" in window.body.toPlainText()
    window.show_error("Rate limited.")
    assert window.ask.isEnabled() and window.status.text() == "Rate limited."


def test_copy_puts_the_thread_on_the_clipboard_as_markdown(window):
    from PySide6.QtGui import QGuiApplication

    window.list.setCurrentRow(1)
    assert window.copy.isEnabled()
    window.copy.click()
    text = QGuiApplication.clipboard().text()
    assert text.startswith("**what is the code distance?**\n\nThe **minimum** weight of a logical.")
    assert "**why odd?**\n\nMajority vote." in text and "· m</sub>" in text
    assert window.status.text() == "Copied 2 questions as Markdown"
    window.list.setCurrentRow(0)
    window._copy()
    assert window.status.text() == "Copied 1 question as Markdown"


def test_copy_is_disabled_without_a_thread(qtbot, window):
    window.search.setText("zzz")
    qtbot.waitUntil(lambda: window.list.count() == 0)
    assert not window.copy.isEnabled()
    window._copy()  # the shortcut does nothing either
    assert "Copied" not in window.status.text()


def test_copy_works_while_a_follow_up_is_being_answered(window):
    window.show_thinking("q")
    assert window.copy.isEnabled()


def test_markers_are_drawn_where_the_answer_pointed(qtbot, tmp_path):
    from helpers import make_snapshot

    log = DoubtLog(tmp_path)
    snap = make_snapshot(logical=(800, 500), cursor=(100, 100))
    log.add("q", "a", Image.new("RGB", (400, 250)), "m", snap=snap, points=[(400, 250, "centre")])
    w = JournalWindow(Journal(tmp_path))
    qtbot.addWidget(w)
    w.refresh()
    assert w.shot.points == [(200.0, 125.0, "centre")], "logical screen point -> saved-shot pixel"
    w.shot.resize(400, 250)
    w.shot.grab()  # paints the markers without error


def test_an_empty_journal(qtbot, tmp_path):
    w = JournalWindow(Journal(tmp_path))
    qtbot.addWidget(w)
    w.refresh()
    assert w.list.count() == 0 and "Nothing here yet" in w.body.toPlainText()
    assert "Click the orb" in w.body.toPlainText(), "an empty view says what to do"


def test_double_click_opens_the_full_screenshot(qtbot, window, monkeypatch):
    opened = []
    monkeypatch.setattr("marginalia.ui.journal.QDesktopServices.openUrl", lambda url: opened.append(url))
    window.shot.mouseDoubleClickEvent(None)
    assert opened and opened[0].toLocalFile().endswith(".png")


def test_open_backfills_and_shows(qtbot, window):
    window.open()
    assert window.isVisible()
    window.list.setCurrentRow(0)
    assert window.list.currentItem().data(Qt.UserRole).id == window.thread.id


def test_find_focuses_search_and_escape_closes(qtbot, window):
    from PySide6.QtGui import QKeySequence, QShortcut

    window.show()
    shortcuts = {sc.key().toString(): sc for sc in window.findChildren(QShortcut)}
    shortcuts[QKeySequence(QKeySequence.Find).toString()].activated.emit()
    assert window.search.selectedText() == window.search.text()
    shortcuts[QKeySequence(Qt.Key_Escape).toString()].activated.emit()
    assert not window.isVisible()


def test_an_empty_journal_shows_one_message_and_nothing_to_press(qtbot, tmp_path):
    w = JournalWindow(Journal(tmp_path))
    qtbot.addWidget(w)
    w.refresh()
    assert not w.ask_row.isVisibleTo(w) and not w.body.isVisibleTo(w)
    assert w.shot.empty and w.shot.missing.startswith("Nothing here yet")
    w.shot.resize(600, 400)
    w.shot.grab()  # paints the mark and the message without error


def test_a_thread_names_its_model_in_words(qtbot, tmp_path):
    log = DoubtLog(tmp_path)
    log.add("q", "a", Image.new("RGB", (40, 25)), "claude-sonnet-5-5")
    w = JournalWindow(Journal(tmp_path))
    qtbot.addWidget(w)
    w.refresh()
    assert "Claude Sonnet 5.5" in w.body.toPlainText() and "claude-sonnet-5-5" not in w.body.toPlainText()
    assert w.ask_row.isVisibleTo(w) and not w.status.isVisibleTo(w), "no empty status line leaving a gap"
    w.list.viewport().grab()  # the two-line rows paint without error


def test_one_thread_is_not_one_threads(qtbot, tmp_path):
    log = DoubtLog(tmp_path)
    log.add("q", "a", Image.new("RGB", (40, 25)), "m")
    w = JournalWindow(Journal(tmp_path))
    qtbot.addWidget(w)
    w.refresh()
    assert w.count.text() == "1 thread"
