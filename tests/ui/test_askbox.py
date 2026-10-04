"""The ask box: submitting, cancelling, switching to voice, staying on screen."""

from PySide6.QtCore import QPoint, QRect, Qt

from marginalia.ui import (
    AskBox,
)

SCREEN = QRect(0, 0, 1440, 900)


def test_ask_box_submits_trimmed_text(qtbot):
    box = AskBox()
    qtbot.addWidget(box)
    box.open_at(QPoint(300, 300), SCREEN)
    box.edit.setText("  what is this?  ")
    with qtbot.waitSignal(box.submitted) as sig:
        qtbot.keyClick(box.edit, Qt.Key_Return)
    assert sig.args == ["what is this?"] and not box.isVisible()


def test_ask_box_ignores_empty_question(qtbot):
    box = AskBox()
    qtbot.addWidget(box)
    box.open_at(QPoint(300, 300), SCREEN)
    with qtbot.assertNotEmitted(box.submitted):
        qtbot.keyClick(box.edit, Qt.Key_Return)


def test_ask_box_mic_switches_to_voice(qtbot):
    box = AskBox()
    qtbot.addWidget(box)
    box.open_at(QPoint(300, 300), SCREEN)
    with qtbot.waitSignal(box.voice_requested):
        qtbot.mouseClick(box.mic, Qt.LeftButton)
    box.set_voice_available(False)
    assert not box.mic.isVisibleTo(box)


def test_ask_box_esc_cancels(qtbot):
    box = AskBox()
    qtbot.addWidget(box)
    box.open_at(QPoint(300, 300), SCREEN)
    with qtbot.waitSignal(box.cancelled):
        qtbot.keyClick(box, Qt.Key_Escape)


def test_ask_box_stays_on_screen_near_the_bottom(qtbot):
    box = AskBox()
    qtbot.addWidget(box)
    box.open_at(QPoint(1430, 890), SCREEN)
    assert SCREEN.contains(box.geometry())
