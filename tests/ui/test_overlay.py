"""The pointer overlay that flies markers to targets."""

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF
from PySide6.QtGui import QImage

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


@pytest.fixture
def overlay(qtbot):
    o = PointerOverlay()
    qtbot.addWidget(o)
    return o


def _amber_near(img: QImage, x: int, y: int, r: int = 18) -> bool:
    for dx in range(-r, r + 1, 2):
        for dy in range(-r, r + 1, 2):
            c = img.pixelColor(x + dx, y + dy)
            if c.alpha() > 0 and c.red() > 200 and 120 < c.green() < 210 and c.blue() < 90:
                return True
    return False


def _frame(o: PointerOverlay, t: float) -> QImage:
    o.frozen_at = t  # paint the animation as it looks t seconds in
    img = QImage(o.size(), QImage.Format_ARGB32)
    img.fill(0)
    o.render(img)
    return img


def test_marker_flies_from_the_cursor_and_lands_on_the_target(overlay):
    overlay.point_to(SCREEN, QPoint(700, 450), [(300.0, 200.0, "eq 4")])
    assert _amber_near(_frame(overlay, 0.02), 700, 450), "starts at the cursor"
    landed = _frame(overlay, 3.0)
    assert _amber_near(landed, 300, 200), "ends on the target"
    assert not _amber_near(landed, 700, 450), "and has left the cursor"


def test_every_target_gets_its_own_marker(overlay):
    overlay.point_to(SCREEN, QPoint(700, 450), [(300.0, 200.0, "a"), (1100.0, 700.0, "b")])
    landed = _frame(overlay, 3.0)
    assert _amber_near(landed, 300, 200) and _amber_near(landed, 1100, 700)


def test_coordinates_are_relative_to_the_screen_the_overlay_covers(overlay):
    second = QRect(1440, 0, 1440, 900)
    overlay.point_to(second, QPoint(1440 + 700, 450), [(1440 + 300.0, 200.0, "x")])
    assert overlay.geometry() == second
    assert overlay.targets[0][0] == QPointF(300, 200)


def test_animation_comes_to_rest(qtbot, overlay):
    overlay.TRAVEL, overlay.STAGGER, overlay.SETTLE = 0.02, 0.0, 0.02
    overlay.point_to(SCREEN, QPoint(700, 450), [(300.0, 200.0, "x")])
    assert overlay.tick.isActive()
    qtbot.waitUntil(lambda: not overlay.tick.isActive(), timeout=1000)
    assert overlay.frozen_at is not None, "no repaint loop left running once settled"


def test_label_sits_above_right_of_the_marker(overlay):
    bounds = QRectF(SCREEN)
    r = overlay.label_rect(QPointF(300, 200), "eq 4", bounds)
    assert r.left() > 300 and r.bottom() < 200


def test_label_flips_left_at_the_right_edge_and_below_at_the_top(overlay):
    bounds = QRectF(SCREEN)
    r = overlay.label_rect(QPointF(1430, 10), "a long label here", bounds)
    assert r.right() < 1430 and r.top() > 10
    assert bounds.contains(r)
