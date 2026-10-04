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
