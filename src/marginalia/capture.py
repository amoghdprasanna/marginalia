"""Screen capture and image preparation.

Three coordinate spaces show up here:
  logical   Qt's global desktop coordinates, which the overlay draws in
  physical  pixels of the captured screenshot (logical * devicePixelRatio)
  sent      pixels of the resized images the model sees; it answers in these

We resize images ourselves to exactly the size Claude would resize them to, so the
coordinates it returns map one-to-one onto the images we sent (no silent drift).
"""
from __future__ import annotations

import base64
import io
import math
import time
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

STANDARD_TIER = (1568, 1568)  # (max long edge px, max visual tokens)
HIRES_TIER = (2576, 4784)

ZOOM_LOGICAL = (620, 380)  # area around the cursor, in logical px, sent as a close-up
ZOOM_TARGET_W = 1100  # upscale small crops to about this width so tiny text stays legible
RING_RGB = (255, 45, 85)


def count_image_tokens(width: int, height: int) -> int:
    return math.ceil(width / 28) * math.ceil(height / 28)


def resized_size(width: int, height: int, max_edge: int = 1568, max_tokens: int = 1568) -> tuple[int, int]:
    """The size Claude resizes an image to before padding (reference algorithm from the API docs)."""

    def fits(w: int, h: int) -> bool:
        return (
            math.ceil(w / 28) * 28 <= max_edge
            and math.ceil(h / 28) * 28 <= max_edge
            and count_image_tokens(w, h) <= max_tokens
        )

    if fits(width, height):
        return (width, height)
    if height > width:
        rh, rw = resized_size(height, width, max_edge, max_tokens)
        return (rw, rh)
    aspect = width / height
    lo, hi = 1, width
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if fits(mid, max(round(mid / aspect), 1)):
            lo = mid
        else:
            hi = mid
    return (lo, max(round(lo / aspect), 1))


@dataclass
class Snapshot:
    image: Image.Image  # physical pixels of one screen
    screen_geo: tuple[int, int, int, int]  # logical x, y, w, h of that screen
    cursor: tuple[int, int]  # logical global cursor position
    taken_at: float = field(default_factory=time.time)

    @property
    def cursor_physical(self) -> tuple[float, float]:
        gx, gy, gw, gh = self.screen_geo
        w, h = self.image.size
        return ((self.cursor[0] - gx) * w / gw, (self.cursor[1] - gy) * h / gh)

    def physical_to_logical(self, px: float, py: float) -> tuple[float, float]:
        gx, gy, gw, gh = self.screen_geo
        w, h = self.image.size
        return (gx + px * gw / w, gy + py * gh / h)


@dataclass
class Prepared:
    full: Image.Image  # image 1 as the model sees it (with cursor ring)
    zoom: Image.Image  # image 2: close-up around the cursor (with cursor ring)
    full_scale: tuple[float, float]  # physical px per sent px
    zoom_origin: tuple[int, int]  # crop top-left, physical px
    zoom_scale: tuple[float, float]  # physical px per zoom px
    cursor_full: tuple[int, int]
    cursor_zoom: tuple[int, int]

    def to_physical(self, image: str, x: float, y: float) -> tuple[float, float]:
        if image == "zoom":
            x = min(max(x, 0), self.zoom.width)
            y = min(max(y, 0), self.zoom.height)
            return (self.zoom_origin[0] + x * self.zoom_scale[0], self.zoom_origin[1] + y * self.zoom_scale[1])
        x = min(max(x, 0), self.full.width)
        y = min(max(y, 0), self.full.height)
        return (x * self.full_scale[0], y * self.full_scale[1])

    def physical_to_full(self, px: float, py: float) -> tuple[int, int]:
        return (round(px / self.full_scale[0]), round(py / self.full_scale[1]))


def draw_ring(img: Image.Image, center: tuple[float, float], r: int) -> None:
    """Hollow ring so the text under the cursor stays readable to the model."""
    d = ImageDraw.Draw(img)
    x, y = center
    d.ellipse((x - r - 1, y - r - 1, x + r + 1, y + r + 1), outline=(255, 255, 255), width=5)
    d.ellipse((x - r, y - r, x + r, y + r), outline=RING_RGB, width=3)


def prepare(snap: Snapshot, hires: bool = False) -> Prepared:
    max_edge, max_tokens = HIRES_TIER if hires else STANDARD_TIER
    src = snap.image
    W, H = src.size

    fw, fh = resized_size(W, H, max_edge, max_tokens)
    full = src.resize((fw, fh), Image.LANCZOS) if (fw, fh) != (W, H) else src.copy()
    fsx, fsy = W / fw, H / fh
    cpx, cpy = snap.cursor_physical
    cursor_full = (round(cpx / fsx), round(cpy / fsy))

    dpr = W / snap.screen_geo[2]
    cw = min(W, round(ZOOM_LOGICAL[0] * dpr))
    ch = min(H, round(ZOOM_LOGICAL[1] * dpr))
    x0 = int(min(max(cpx - cw / 2, 0), W - cw))
    y0 = int(min(max(cpy - ch / 2, 0), H - ch))
    crop = src.crop((x0, y0, x0 + cw, y0 + ch))
    up = min(2.0, max(1.0, ZOOM_TARGET_W / cw))
    zw, zh = resized_size(round(cw * up), round(ch * up), max_edge, max_tokens)
    zoom = crop.resize((zw, zh), Image.LANCZOS) if (zw, zh) != (cw, ch) else crop
    zsx, zsy = cw / zw, ch / zh
    cursor_zoom = (round((cpx - x0) / zsx), round((cpy - y0) / zsy))

    draw_ring(full, cursor_full, 13)
    draw_ring(zoom, cursor_zoom, 18)
    return Prepared(full, zoom, (fsx, fsy), (x0, y0), (zsx, zsy), cursor_full, cursor_zoom)


def to_b64_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


# Qt-specific capture (imported lazily so the rest of this module is testable without a display).

def qimage_to_pil(qimg) -> Image.Image:
    from PySide6.QtGui import QImage

    qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, bpl = qimg.width(), qimg.height(), qimg.bytesPerLine()
    data = bytes(qimg.constBits())
    return Image.frombuffer("RGBA", (w, h), data, "raw", "RGBA", bpl, 1).convert("RGB")


def grab_screen(x: int, y: int) -> Snapshot:
    """Capture the whole screen that contains the logical point (x, y)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.screenAt(QPoint(int(x), int(y))) or QGuiApplication.primaryScreen()
    g = screen.geometry()
    pix = screen.grabWindow(0)
    img = qimage_to_pil(pix.toImage())

    # Some platforms hand back the whole virtual desktop; crop to this screen if so.
    dpr = pix.devicePixelRatio() or screen.devicePixelRatio() or 1.0
    vg = screen.virtualGeometry()
    if abs(img.width / dpr - g.width()) > 2 and abs(img.width / dpr - vg.width()) <= 2:
        left, top = round((g.x() - vg.x()) * dpr), round((g.y() - vg.y()) * dpr)
        img = img.crop((left, top, left + round(g.width() * dpr), top + round(g.height() * dpr)))

    if img.getbbox() is None:
        raise RuntimeError(
            "The screenshot came back blank. On macOS, allow Screen Recording for your terminal "
            "or Python in System Settings > Privacy & Security, then restart it."
        )
    return Snapshot(img, (g.x(), g.y(), g.width(), g.height()), (int(x), int(y)))
