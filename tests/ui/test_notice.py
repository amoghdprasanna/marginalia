"""The small message window used for crash reports and updates."""

from marginalia.ui import Notice


def test_it_is_as_tall_as_its_words_and_no_taller(qtbot):
    """Bug: a long message left wide empty bands above and below it."""
    text = "Something went wrong while answering. " * 6
    n = Notice("Marginalia hit a problem", text, [("Not now", None), ("Review…", None)])
    qtbot.addWidget(n)
    n.open()
    assert n.height() == n.layout().totalHeightForWidth(n.width())
    assert n.text.height() >= n.text.heightForWidth(n.text.width()), "every line shown"
    n.close()


def test_the_message_reads_as_body_text_and_the_last_button_is_the_main_one(qtbot):
    n = Notice("Update", "You have 0.1.0.", [("Later", None), ("Update now", None)])
    qtbot.addWidget(n)
    assert n.text.objectName() != "muted"
    assert n.buttons["Update now"].objectName() == "primary" and n.buttons["Update now"].isDefault()


def test_focusing_a_button_does_not_resize_it(qtbot):
    """Bug: the focus ring was a thicker border added on top, so a focused button grew and its text
    was squashed (the bubble's 'Try again')."""
    from marginalia.ui import AnswerBubble

    b = AnswerBubble()
    qtbot.addWidget(b)
    b.show_error("q", "Rate limited.", [("Try again", lambda: None), ("Open Settings", lambda: None)])
    b.show()
    for button in b.action_buttons.values():
        before = button.sizeHint()
        button.setFocus()
        qtbot.waitUntil(button.hasFocus)
        button.style().unpolish(button)
        button.style().polish(button)
        assert button.sizeHint() == before, button.text()
