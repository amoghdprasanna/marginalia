"""The orb: click to ask, drag to move, spin while busy, right-click menu."""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
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
        drag(orb, QPoint(-40, 30))
    assert orb.pos() == start + QPoint(-40, 30)


def test_spins_while_busy_and_rests_after(qtbot, orb):
    orb.set_busy(True)
    qtbot.waitUntil(lambda: orb.phase > 1.2)
    orb.set_busy(False)
    assert orb.phase == 0.9 and not orb._spin.isActive()


@pytest.mark.parametrize(
    ("label", "signal"),
    [
        ("Ask by typing", "type_requested"),
        ("Ask by voice", "voice_requested"),
        ("About Marginalia…", "about_requested"),
        ("Quit Marginalia", "quit_requested"),
    ],
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


def test_an_orb_dragged_off_the_screen_comes_back(qtbot, orb):
    """Bug: the orb could be dropped past the screen edge, and with no hotkey the app was unreachable."""
    area = orb.screen().availableGeometry()
    drag(orb, QPoint(area.width() * 3, area.height() * 3))
    assert area.contains(orb.frameGeometry())


def test_an_orb_on_a_screen_that_went_away_comes_back(qtbot, orb):
    area = orb.screen().availableGeometry()
    orb.move(area.right() + 5000, area.top())  # where an unplugged monitor used to be
    orb.rehome()
    assert area.contains(orb.frameGeometry())


def test_with_one_screen_following_the_pointer_leaves_the_orb_alone(qtbot, orb):
    before = orb.pos()
    orb.follow_pointer(QPoint(-10000, -10000))
    assert orb.pos() == before


class FakeScreen:
    def __init__(self, x, y, w, h):
        self.area = QRect(x, y, w, h)

    def availableGeometry(self):  # noqa: N802
        return self.area


@pytest.fixture
def two_screens(monkeypatch):
    """A laptop and a bigger monitor to its right; screenAt answers from their areas."""
    import marginalia.ui.orb as orb_module

    screens = [FakeScreen(0, 0, 1440, 900), FakeScreen(1440, -200, 2560, 1440)]

    def screen_at(p):
        return next((s for s in screens if s.area.contains(p)), None)

    monkeypatch.setattr(orb_module, "QGuiApplication", SimpleNamespace(screens=lambda: screens, screenAt=screen_at))
    return screens


def test_the_orb_follows_the_pointer_to_another_display(qtbot, orb, two_screens):
    """Bug: a window lives on one display, so the orb stayed behind on the one it started on."""
    laptop, monitor = two_screens
    orb.move(1440 - orb.SIZE - 18, 426)  # tucked against the laptop's right edge, halfway down
    orb.follow_pointer(QPoint(2500, 300))
    assert monitor.area.contains(orb.geometry())
    assert monitor.area.right() - orb.geometry().right() < 40, "still against the right edge"
    orb.follow_pointer(QPoint(100, 100))
    assert laptop.area.contains(orb.geometry()), "and back again"


def test_the_orb_stays_while_the_pointer_is_on_its_display(qtbot, orb, two_screens):
    orb.move(1300, 400)
    orb.follow_pointer(QPoint(200, 200))
    assert orb.pos() == QPoint(1300, 400)


def test_the_orb_stays_when_the_pointer_is_on_no_display(qtbot, orb, two_screens):
    orb.move(1300, 400)
    orb.follow_pointer(QPoint(-5000, -5000))
    assert orb.pos() == QPoint(1300, 400)


def test_the_orb_does_not_jump_away_mid_drag(qtbot, orb, two_screens):
    orb.move(1300, 400)
    QTest.mousePress(orb, Qt.LeftButton, Qt.NoModifier, QPoint(orb.SIZE // 2, orb.SIZE // 2))
    orb.follow_pointer(QPoint(2500, 300))
    assert orb.pos() == QPoint(1300, 400)
    QTest.mouseRelease(orb, Qt.LeftButton, Qt.NoModifier, QPoint(orb.SIZE // 2, orb.SIZE // 2))


def test_a_hidden_orb_does_not_follow(qtbot, orb, two_screens):
    orb.move(1300, 400)
    orb.hide()
    orb.follow_pointer(QPoint(2500, 300))
    assert orb.pos() == QPoint(1300, 400)


def test_the_orb_keeps_watching_the_pointer(qtbot, orb):
    assert orb._follow.isActive() and orb._follow.interval() <= 1000
