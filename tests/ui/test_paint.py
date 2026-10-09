"""The qubit mark and line icons render without errors."""

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from marginalia.ui import (
    draw_icon,
    draw_qubit,
)


@pytest.mark.parametrize("kind", ["mic", "keys", "send", "unknown"])
def test_icons_and_qubit_paint(qapp, kind):
    img = QImage(40, 40, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    draw_icon(p, kind, QRectF(4, 4, 32, 32), QColor("#FFB224"))
    draw_qubit(p, QPointF(20, 20), 10, 1.0)
    p.end()
    assert img.pixelColor(30, 20).alpha() > 0  # the qubit ring's right edge


def test_app_icon_has_every_taskbar_size(qapp):
    from marginalia.ui.paint import app_icon, app_icon_image

    img = app_icon_image(64)
    assert img.width() == 64 and img.pixelColor(32, 32).alpha() == 255, "the disc is opaque in the middle"
    assert img.pixelColor(0, 0).alpha() == 0, "the corners are transparent"
    assert {s.width() for s in app_icon().availableSizes()} >= {16, 32, 256}


# every desktop (macOS Spaces) ------------------------------------------------------------------


class FakeNSWindow:
    def __init__(self, behaviour=0):
        self.behaviour = behaviour

    def collectionBehavior(self):  # noqa: N802
        return self.behaviour

    def setCollectionBehavior_(self, value):  # noqa: N802
        self.behaviour = value


def test_floating_windows_join_every_desktop_and_full_screen_apps(monkeypatch):
    """Bug: the orb and bubble stayed on the desktop the app started on."""
    from marginalia.ui.theme import CAN_JOIN_ALL_SPACES, FULL_SCREEN_AUXILIARY, join_all_spaces

    monkeypatch.setattr("sys.platform", "darwin")
    win = FakeNSWindow(behaviour=(1 << 3) | (1 << 1))  # what Qt sets on a tool window, plus another bit
    assert join_all_spaces(object(), find=lambda w: win)
    assert win.behaviour & CAN_JOIN_ALL_SPACES and win.behaviour & FULL_SCREEN_AUXILIARY
    assert not win.behaviour & (1 << 1), "MoveToActiveSpace must go: AppKit rejects it with CanJoinAllSpaces"
    assert win.behaviour & (1 << 3), "keeps the rest of what Qt had set"


def test_every_show_reapplies_it(qtbot, monkeypatch):
    import marginalia.ui.theme as theme
    from marginalia.ui import Orb

    monkeypatch.setattr("sys.platform", "darwin")
    applied = []
    monkeypatch.setattr(theme, "join_all_spaces", lambda w: applied.append(type(w).__name__))
    orb = Orb(None)
    qtbot.addWidget(orb)
    orb.show()
    orb.hide()
    orb.show()
    assert applied.count("Orb") == 2


def test_no_native_window_off_cocoa(qapp):
    from PySide6.QtWidgets import QWidget

    from marginalia.ui.theme import ns_window

    assert ns_window(QWidget()) is None, "offscreen winIds are not NSViews; never touch them"


def test_other_platforms_are_left_alone(monkeypatch):
    from marginalia.ui.theme import join_all_spaces

    monkeypatch.setattr("sys.platform", "linux")
    assert not join_all_spaces(object(), find=lambda w: pytest.fail("not asked"))
