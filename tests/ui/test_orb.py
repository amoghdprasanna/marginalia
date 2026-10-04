"""The orb: click to ask, drag to move, spin while busy, right-click menu."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from marginalia.ui import Orb


@pytest.fixture
def orb(qtbot):
    o = Orb("Ctrl+Alt+Space")
    qtbot.addWidget(o)
    o.show()
    return o


def drag(orb, by: QPoint):
    centre = QPoint(orb.SIZE // 2, orb.SIZE // 2)
    QTest.mousePress(orb, Qt.LeftButton, Qt.NoModifier, centre)
    QTest.mouseMove(orb, centre + by)
    QTest.mouseRelease(orb, Qt.LeftButton, Qt.NoModifier, centre + by)


def test_click_asks(qtbot, orb):
    with qtbot.waitSignal(orb.clicked, timeout=500):
        drag(orb, QPoint(0, 0))


def test_a_little_hand_shake_is_still_a_click(qtbot, orb):
    with qtbot.waitSignal(orb.clicked, timeout=500):
        drag(orb, QPoint(2, 2))


def test_dragging_moves_the_orb_and_does_not_ask(qtbot, orb):
    start = orb.pos()
    with qtbot.assertNotEmitted(orb.clicked):
        drag(orb, QPoint(40, 30))
    assert orb.pos() == start + QPoint(40, 30)


def test_spins_while_busy_and_rests_after(qtbot, orb):
    orb.set_busy(True)
    qtbot.waitUntil(lambda: orb.phase > 1.2)
    orb.set_busy(False)
    assert orb.phase == 0.9 and not orb._spin.isActive()


@pytest.mark.parametrize(
    ("label", "signal"),
    [("Ask by typing", "type_requested"), ("Ask by voice", "voice_requested"), ("Quit Marginalia", "quit_requested")],
)
def test_menu_actions(qtbot, orb, label, signal):
    actions = {a.text(): a for a in orb.build_menu().actions() if a.text()}
    with qtbot.waitSignal(getattr(orb, signal), timeout=500):
        actions[label].trigger()


def test_tooltip_mentions_the_shortcut_only_when_there_is_one(qtbot):
    with_key, without = Orb("Ctrl+Alt+Space"), Orb(None)
    qtbot.addWidget(with_key)
    qtbot.addWidget(without)
    assert "Ctrl+Alt+Space" in with_key.toolTip()
    assert "Shortcut" not in without.toolTip()
