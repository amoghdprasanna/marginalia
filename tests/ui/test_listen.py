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


def test_an_old_problem_does_not_hide_a_newer_question(qtbot, listen):
    """Bug: the problem state's 2.6 s auto-hide fired on whatever the box showed by then.

    Asking again quickly and finishing inside that window hid the "Transcribing" box, and the
    controller then dropped the transcript because the box was no longer visible.
    """
    listen.show_problem("Didn't catch that.")
    listen.open_at(QPoint(300, 300), SCREEN, lambda: 0.0)  # tries again straight away
    listen.show_transcribing()  # not listening any more, but busy with the new question
    qtbot.wait(2800)
    assert listen.isVisible()


def test_a_problem_still_closes_itself(qtbot, listen):
    listen.show_problem("Didn't catch that.")
    qtbot.waitUntil(lambda: not listen.isVisible(), timeout=4000)


def test_holding_ignores_pauses_until_released(qtbot):
    w = ListenBox(SilenceDetector(silence_s=0.0, calibrate_s=0.0, max_s=100))
    qtbot.addWidget(w)
    w.detector.heard_speech = True  # spoke, then went quiet
    with qtbot.assertNotEmitted(w.stop_requested, wait=200):
        w.open_at(QPoint(300, 300), SCREEN, lambda: 0.0, hold=True)
        w.detector.heard_speech = True
    assert "release" in w.hint.text()
    with qtbot.waitSignal(w.stop_requested, timeout=1000):
        w.release_hold()
        w.detector.heard_speech = True
    assert "pause" in w.hint.text()


def test_finish_sends_once(qtbot, listen):
    with qtbot.waitSignal(listen.stop_requested):
        listen.finish()
    with qtbot.assertNotEmitted(listen.stop_requested):
        listen.finish()


def test_no_audio_at_all_is_reported_instead_of_waiting_forever(qtbot):
    """Bug: a mic still switching modes delivered nothing; listening waited silently for 45 s."""
    w = ListenBox(SilenceDetector(max_s=100))
    qtbot.addWidget(w)
    w.NO_AUDIO_S = 0.2
    with qtbot.waitSignal(w.no_audio, timeout=2000):
        w.open_at(QPoint(300, 300), SCREEN, lambda: 0.0, device="Amogh's AirPods Pro")
    assert "AirPods" in w.device_lab.text()


def test_a_quiet_but_real_microphone_is_not_no_audio(qtbot):
    w = ListenBox(SilenceDetector(max_s=100))
    qtbot.addWidget(w)
    w.NO_AUDIO_S = 0.2
    with qtbot.assertNotEmitted(w.no_audio, wait=500):
        w.open_at(QPoint(300, 300), SCREEN, lambda: 0.002)


def test_problems_wrap_and_stay_long_enough_to_read(qtbot, listen):
    listen.show_problem("No sound from Amogh's AirPods Pro. Pick another input in System Settings › Sound.")
    assert listen.status.wordWrap()
    qtbot.wait(2800)
    assert listen.isVisible(), "a long message isn't gone before you've read it"
