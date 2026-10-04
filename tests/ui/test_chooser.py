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
