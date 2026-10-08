"""The answer bubble: thinking, answer and error states, copy, follow-ups, Esc."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

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


# streaming ------------------------------------------------------------------------------


def test_partial_answer_shows_writing_and_hides_actions(bubble):
    bubble.show_thinking("q")
    bubble.show_partial("q", "The distance **is")
    assert not bubble.status.isVisible() and bubble.body.isVisible()
    assert bubble.meta.text() == "Writing…"
    assert not bubble.copy_btn.isVisible() and not bubble.follow_wrap.isVisible()


def test_long_partial_follows_the_newest_words(bubble):
    bubble.show_partial("q", "\n\n".join(f"Paragraph {i} of a long derivation." for i in range(60)))
    bar = bubble.body.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == bar.maximum()


def test_finished_answer_is_read_from_the_top(bubble):
    long = "\n\n".join(f"Paragraph {i}." for i in range(60))
    bubble.show_partial("q", long)
    bubble.show_answer("q", long, "meta")
    assert bubble.body.verticalScrollBar().value() == 0
    assert bubble.copy_btn.isVisible() and bubble.follow_wrap.isVisible()


def test_copy_after_streaming_copies_the_final_text(qtbot, bubble):
    bubble.show_partial("q", "Half")
    bubble.show_answer("q", "Whole answer.", "meta")
    bubble._copy()
    assert QGuiApplication.clipboard().text() == "Whole answer."


# dragging -------------------------------------------------------------------------------


def test_bubble_drags_by_its_header(bubble):
    bubble.show_answer("q", "answer", "meta")
    start = bubble.pos()
    QTest.mousePress(bubble, Qt.LeftButton, Qt.NoModifier, QPoint(100, 15))
    QTest.mouseMove(bubble, QPoint(160, 55))
    QTest.mouseRelease(bubble, Qt.LeftButton, Qt.NoModifier, QPoint(160, 55))
    assert bubble.pos() == start + QPoint(60, 40)


def test_bubble_does_not_drag_from_its_body(bubble):
    bubble.show_answer("q", "answer", "meta")
    start = bubble.pos()
    y = bubble.height() - 10
    QTest.mousePress(bubble, Qt.LeftButton, Qt.NoModifier, QPoint(100, y))
    QTest.mouseMove(bubble, QPoint(160, y + 40))
    assert bubble.pos() == start


# telling you what is happening and what to do next ------------------------------------------


def test_working_shows_a_stop_and_then_the_seconds(bubble, monkeypatch):
    bubble.show_thinking("q")
    assert bubble.stop_btn.isVisibleTo(bubble), "a visible way out while you wait"
    assert not bubble.copy_btn.isVisibleTo(bubble)
    monkeypatch.setattr(bubble, "_clock", type("C", (), {"elapsed": lambda self: 7400})())
    bubble._tick_dots()
    assert bubble.status.text().startswith("Thinking") and bubble.status.text().endswith("7 s")


def test_stop_ends_the_thread(qtbot, bubble):
    bubble.show_thinking("q")
    with qtbot.waitSignal(bubble.closed):
        bubble.stop_btn.click()


def test_answer_footer_is_short_with_details_on_hover(bubble):
    bubble.show_answer("q", "a", "Answered in 4.2 s", "claude-opus-5-5, done after 4.2 s", points=2)
    assert bubble.meta.text() == "Answered in 4.2 s" and "claude-opus-5-5" in bubble.meta.toolTip()
    assert not bubble.stop_btn.isVisibleTo(bubble)


def test_markers_can_be_shown_again(qtbot, bubble):
    bubble.show_answer("q", "a", "m", points=2)
    assert bubble.replay_btn.isVisibleTo(bubble) and "2 places" in bubble.replay_btn.text()
    with qtbot.waitSignal(bubble.replay_requested):
        bubble.replay_btn.click()
    bubble.show_answer("q", "a", "m", points=0)
    assert not bubble.replay_btn.isVisibleTo(bubble), "nothing was pointed at, nothing to replay"


def test_an_error_offers_its_fix_first_and_hides_the_follow_up(bubble):
    ran = []
    bubble.show_error("q", "Too many requests.", [("Try again", lambda: ran.append("retry")), ("Later", print)])
    assert list(bubble.action_buttons) == ["Try again", "Later"]
    assert bubble.action_buttons["Try again"].objectName() == "primary"
    assert not bubble.follow_wrap.isVisibleTo(bubble) and not bubble.footer.isVisibleTo(bubble)
    bubble.action_buttons["Try again"].click()
    assert ran == ["retry"]


def test_an_error_without_a_fix_lets_you_rephrase(bubble):
    bubble.show_error("q", "Claude declined to answer this one.")
    assert bubble.follow_wrap.isVisibleTo(bubble) and not bubble.actions.isVisibleTo(bubble)


def test_an_answer_after_an_error_clears_the_error_state(bubble):
    bubble.show_error("q", "Failed.", [("Try again", print)])
    bubble.show_answer("q", "Fine now.", "m")
    assert not bubble._failed and not bubble.actions.isVisibleTo(bubble)
    bubble.grab()  # paints the normal mark again
