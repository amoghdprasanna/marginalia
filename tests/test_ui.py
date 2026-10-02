"""Widgets: signals, keyboard paths and rendering, driven offscreen with pytest-qt."""

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from marginalia.ui import (
    AnswerBubble,
    AskBox,
    ListenBox,
    ModeChooser,
    PointerOverlay,
    draw_icon,
    draw_qubit,
)
from marginalia.voice import SilenceDetector

pytestmark = pytest.mark.qt
SCREEN = QRect(0, 0, 1440, 900)


@pytest.fixture
def chooser(qtbot):
    w = ModeChooser()
    qtbot.addWidget(w)
    w.open_beside(QRect(1380, 400, 48, 48), SCREEN)
    return w


@pytest.mark.parametrize(
    ("key", "mode"), [(Qt.Key_T, "type"), (Qt.Key_Return, "type"), (Qt.Key_V, "voice"), (Qt.Key_Space, "voice")]
)
def test_chooser_keys(qtbot, chooser, key, mode):
    with qtbot.waitSignal(chooser.chosen) as sig:
        qtbot.keyClick(chooser, key)
    assert sig.args == [mode] and not chooser.isVisible()


def test_chooser_buttons(qtbot, chooser):
    with qtbot.waitSignal(chooser.chosen) as sig:
        qtbot.mouseClick(chooser.voice_btn, Qt.LeftButton)
    assert sig.args == ["voice"]


def test_chooser_without_voice_ignores_v(qtbot, chooser):
    chooser.set_voice_available(False, "not installed")
    with qtbot.assertNotEmitted(chooser.chosen):
        qtbot.keyClick(chooser, Qt.Key_V)
    assert "not installed" in chooser.voice_btn.toolTip()


def test_chooser_opens_on_the_screen_side_of_the_orb(chooser):
    assert chooser.geometry().right() < 1380  # orb is on the right edge, so the popup goes left
    w = ModeChooser()
    w.open_beside(QRect(10, 400, 48, 48), SCREEN)
    assert w.geometry().left() > 58


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


@pytest.fixture
def listen(qtbot):
    w = ListenBox(SilenceDetector(max_s=100))
    qtbot.addWidget(w)
    w.open_at(QPoint(300, 300), SCREEN, lambda: 0.0)
    return w


def test_enter_sends_once(qtbot, listen):
    with qtbot.waitSignal(listen.stop_requested):
        qtbot.keyClick(listen, Qt.Key_Return)
    with qtbot.assertNotEmitted(listen.stop_requested):
        qtbot.keyClick(listen, Qt.Key_Return)  # already sent


def test_esc_cancels_listening(qtbot, listen):
    with qtbot.waitSignal(listen.cancelled):
        qtbot.keyClick(listen, Qt.Key_Escape)
    assert not listen.isVisible()


def test_detector_ends_listening(qtbot):
    w = ListenBox(SilenceDetector(max_s=0.0))
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.stop_requested, timeout=1000):
        w.open_at(QPoint(300, 300), SCREEN, lambda: 0.0)


def test_listen_states(listen):
    listen.show_transcribing()
    assert listen.status.text().startswith("Transcribing")
    assert not listen.send_btn.isVisibleTo(listen)
    listen.show_problem("Didn't catch that.")
    assert listen.status.text() == "Didn't catch that." and not listen.wave.isVisibleTo(listen)


def test_overlay_shows_and_clears_markers(qtbot):
    o = PointerOverlay()
    qtbot.addWidget(o)
    o.point_to(SCREEN, QPoint(700, 450), [(300.0, 200.0, "eq 4")])
    assert o.isVisible() and len(o.targets) == 1
    o.point_to(SCREEN, QPoint(700, 450), [])
    assert not o.isVisible()


@pytest.mark.parametrize("kind", ["mic", "keys", "send", "unknown"])
def test_icons_and_qubit_paint(qapp, kind):
    img = QImage(40, 40, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    draw_icon(p, kind, QRectF(4, 4, 32, 32), QColor("#FFB224"))
    draw_qubit(p, QPointF(20, 20), 10, 1.0)
    p.end()
    assert img.pixelColor(30, 20).alpha() > 0  # the qubit ring's right edge
