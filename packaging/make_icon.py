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

from PySide6.QtWidgets import QApplication  # noqa: E402

from marginalia.ui.paint import app_icon_image  # noqa: E402

OUT = Path(__file__).resolve().parent / "build"
SIZES = (16, 32, 64, 128, 256, 512, 1024)


def main() -> Path:
    QApplication.instance() or QApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    pngs = {s: OUT / f"icon_{s}.png" for s in SIZES}
    for s, path in pngs.items():
        app_icon_image(s).save(str(path))
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
