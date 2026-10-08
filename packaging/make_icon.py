"""Draw the app icon (the amber qubit on a slate disc) at every size the platforms want.

    python packaging/make_icon.py    # writes packaging/build/icon.icns (macOS) or icon.ico, and PNGs

Drawn with the same code as the orb, so the icon and the app can't drift apart.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from marginalia.ui.paint import draw_qubit  # noqa: E402

OUT = Path(__file__).resolve().parent / "build"
SIZES = (16, 32, 64, 128, 256, 512, 1024)


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    margin = size * 0.09  # the macOS icon grid leaves a margin around the shape
    disc = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    p.setPen(QPen(QColor(255, 255, 255, 40), max(1.0, size / 256)))
    p.setBrush(QColor(27, 32, 49))
    p.drawEllipse(disc)
    draw_qubit(p, QPointF(size / 2, size / 2), disc.width() * 0.3, 0.9, halo=False)
    p.end()
    return img


def main() -> Path:
    QApplication.instance() or QApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    pngs = {s: OUT / f"icon_{s}.png" for s in SIZES}
    for s, path in pngs.items():
        render(s).save(str(path))
    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = OUT / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            shutil.copy(pngs[s], iconset / f"icon_{s}x{s}.png")
            shutil.copy(pngs[s * 2], iconset / f"icon_{s}x{s}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")], check=True)
        return OUT / "icon.icns"
    from PIL import Image

    ico = OUT / "icon.ico"
    Image.open(pngs[256]).save(ico, sizes=[(s, s) for s in (16, 32, 64, 128, 256)])
    return ico


if __name__ == "__main__":
    print(main())
