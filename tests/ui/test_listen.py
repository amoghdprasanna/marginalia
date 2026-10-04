"""The listen box: live mic, end of speech, transcribing and problem states."""

import pytest
from PySide6.QtCore import QPoint, QRect, Qt

from marginalia.ui import (
    ListenBox,
)
from marginalia.voice import SilenceDetector

SCREEN = QRect(0, 0, 1440, 900)


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
