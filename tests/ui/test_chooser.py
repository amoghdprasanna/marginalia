"""The type/speak chooser that pops out of the orb."""

import pytest
from PySide6.QtCore import QRect, Qt

from marginalia.ui import (
    ModeChooser,
)

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


def test_journal_and_settings_are_one_click_from_the_orb(qtbot, chooser):
    with qtbot.waitSignal(chooser.journal_requested):
        chooser.journal_btn.click()
    assert not chooser.isVisible()
    chooser.open_beside(QRect(1380, 400, 48, 48), SCREEN)
    with qtbot.waitSignal(chooser.settings_requested):
        qtbot.keyClick(chooser, Qt.Key_Comma)


def test_the_shortcuts_are_shown_so_they_get_learned(chooser):
    chooser.set_shortcuts("Ctrl+Option+Space", "Ctrl+Option+V")
    assert "Ctrl+Option+Space" in chooser.tip.text() and "hold" in chooser.tip.text()
    chooser.set_shortcuts(None, None)
    assert not chooser.tip.isVisibleTo(chooser)


def test_why_speak_is_off_is_said_out_loud(chooser):
    chooser.set_voice_available(False, "faster-whisper is not installed")
    assert chooser.voice_note.isVisibleTo(chooser) and "faster-whisper" in chooser.voice_note.text()
    chooser.set_voice_available(True)
    assert not chooser.voice_note.isVisibleTo(chooser)
