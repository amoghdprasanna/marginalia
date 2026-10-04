"""The pointer overlay that flies markers to targets."""

from PySide6.QtCore import QPoint, QRect

from marginalia.ui import (
    PointerOverlay,
)

SCREEN = QRect(0, 0, 1440, 900)


def test_overlay_shows_and_clears_markers(qtbot):
    o = PointerOverlay()
    qtbot.addWidget(o)
    o.point_to(SCREEN, QPoint(700, 450), [(300.0, 200.0, "eq 4")])
    assert o.isVisible() and len(o.targets) == 1
    o.point_to(SCREEN, QPoint(700, 450), [])
    assert not o.isVisible()
