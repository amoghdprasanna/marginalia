"""The answer bubble: thinking, answer and error states, copy, follow-ups, Esc."""

import pytest
from PySide6.QtCore import Qt

from marginalia.ui import (
    AnswerBubble,
)


@pytest.fixture
def bubble(qtbot):
    b = AnswerBubble()
    qtbot.addWidget(b)
    b.show()
    return b


def test_first_paragraph_is_not_turned_into_a_bullet(bubble):
    """Regression: paragraph spacing used to copy the last list item's format onto every block."""
    bubble.show_answer("q", "Plain first paragraph.\n\n- one\n- two", "meta")
    first = bubble.body.document().firstBlock()
    assert first.textList() is None
    assert first.text() == "Plain first paragraph."
    assert first.blockFormat().bottomMargin() == 7


def test_thinking_then_answer_states(bubble):
    bubble.show_thinking("what is d?")
    assert bubble.status.isVisibleTo(bubble) and not bubble.body.isVisibleTo(bubble)
    assert bubble.status.text().startswith("Reading your screen")
    bubble.show_answer("what is d?", "The distance.", "fake, 1.0s")
    assert bubble.body.isVisibleTo(bubble) and not bubble.status.isVisibleTo(bubble)
    assert bubble.meta.text() == "fake, 1.0s"


def test_error_hides_copy(bubble):
    bubble.show_error("q", "No API key found.")
    assert "No API key" in bubble.body.toPlainText()
    assert not bubble.copy_btn.isVisibleTo(bubble)


def test_long_question_is_elided_in_the_title(bubble):
    q = "why " * 80
    bubble.show_thinking(q)
    assert len(bubble.title.text()) < len(q) and bubble.title.toolTip() == q


def test_send_button_tracks_follow_up_text(qtbot, bubble):
    bubble.show_answer("q", "a", "m")
    assert not bubble.follow_send.isEnabled()
    bubble.follow.setText("and then?")
    assert bubble.follow_send.isEnabled()
    with qtbot.waitSignal(bubble.followup) as sig:
        qtbot.mouseClick(bubble.follow_send, Qt.LeftButton)
    assert sig.args == ["and then?"]


def test_follow_up_by_voice(qtbot, bubble):
    bubble.show_answer("q", "a", "m")
    with qtbot.waitSignal(bubble.voice_followup):
        qtbot.mouseClick(bubble.follow_mic, Qt.LeftButton)


def test_copy_puts_markdown_on_the_clipboard(qtbot, bubble):
    from PySide6.QtGui import QGuiApplication

    bubble.show_answer("q", "**bold** answer", "m")
    qtbot.mouseClick(bubble.copy_btn, Qt.LeftButton)
    assert QGuiApplication.clipboard().text() == "**bold** answer"
    assert bubble.copy_btn.text() == "Copied"


def test_esc_closes_the_thread(qtbot, bubble):
    with qtbot.waitSignal(bubble.closed):
        qtbot.keyClick(bubble, Qt.Key_Escape)
    assert not bubble.isVisible()
