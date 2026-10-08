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
