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
    assert "No thread matches" in window.body.toPlainText() and not window.ask.isEnabled()


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
