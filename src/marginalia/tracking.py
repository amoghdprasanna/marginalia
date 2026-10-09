"""Keeping markers on what they point at while the screen changes (ADR 0025).

When an answer points at something, we keep a small grayscale picture of what is under each
marker. Once a second while markers are up, the controller hands us a tiny grayscale
screenshot, and for each target we ask:

    still there?   compare the picture with the same spot now, ignoring the pixels our own
                   marker covers (the screenshot includes the overlay)
    moved?         search the whole frame for the picture (normalised cross-correlation)
    gone?          neither matches well: hide the marker until the content comes back

Pure numpy, on images about 480 px wide, so a check costs a few milliseconds.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

WIDTH = 480  # every frame is scaled to this width; marker geometry is measured in these pixels
STAY = 0.80  # correlation at the old spot that means "still there"
FOUND = 0.72  # best correlation elsewhere that means "it moved here"
MIN_CONTRAST = 6.0  # a patch flatter than this (blank page, solid colour) can't be tracked reliably


def to_small_gray(rgb: np.ndarray, width: int = WIDTH) -> np.ndarray:
    """An H x W x 3 uint8 image -> float32 grayscale, `width` px wide (area-averaged)."""
    h, w = rgb.shape[:2]
    k = max(1, round(w / width))
    h2, w2 = h // k * k, w // k * k
    g = rgb[:h2, :w2, :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    return g.reshape(h2 // k, k, w2 // k, k).mean(axis=(1, 3))


def _ncc_masked(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    """Normalised correlation of two equal-size patches over the pixels where mask is True."""
    x, y = a[mask], b[mask]
    if x.size < 16:
        return 0.0
    x, y = x - x.mean(), y - y.mean()
    den = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / den) if den > 1e-6 else 0.0


def match(frame: np.ndarray, patch: np.ndarray) -> tuple[float, int, int]:
    """Best normalised cross-correlation of `patch` anywhere in `frame`: (score, top, left).

    FFT correlation plus integral images for the local means and energies: O(N log N) for the
    whole frame, instead of sliding the patch pixel by pixel.
    """
    fh, fw = frame.shape
    ph, pw = patch.shape
    if ph > fh or pw > fw:
        return 0.0, 0, 0
    p = patch - patch.mean()
    p_norm = float(np.sqrt((p * p).sum()))
    if p_norm < 1e-6:
        return 0.0, 0, 0
    shape = (fh + ph - 1, fw + pw - 1)
    corr = np.fft.irfft2(np.fft.rfft2(frame, shape) * np.conj(np.fft.rfft2(p, shape)), shape)
    corr = corr[: fh - ph + 1, : fw - pw + 1]  # valid placements only (top-left at 0..fh-ph)
    s = np.pad(frame, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    s2 = np.pad(frame * frame, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def box(t):
        return t[ph:, pw:] - t[:-ph, pw:] - t[ph:, :-pw] + t[:-ph, :-pw]

    n = ph * pw
    win_sum, win_sq = box(s), box(s2)
    var = np.maximum(win_sq - win_sum * win_sum / n, 1e-6)
    score = corr / (np.sqrt(var) * p_norm)
    score[var < (MIN_CONTRAST**2) * n * 0.25] = 0.0  # flat windows can't be a real match
    i = int(np.argmax(score))
    top, left = divmod(i, score.shape[1])
    return float(score[top, left]), top, left


@dataclass
class Target:
    patch: np.ndarray
    x: float  # centre, in small-frame pixels
    y: float
    label: str
    label_box: tuple[float, float, float, float]  # where the marker's label sits, relative to the centre
    visible: bool = True
    trackable: bool = True
    misses: int = 0  # checks in a row that couldn't find it; one odd frame mustn't hide a marker


class Tracker:
    """Follows each pointed-at thing from one small frame to the next."""

    def __init__(
        self,
        first: np.ndarray,
        points: list[tuple[float, float, str]],
        patch: tuple[int, int] = (64, 22),
        ring: float = 10.0,
        label_boxes: list[tuple[float, float, float, float]] | None = None,
    ) -> None:
        """`first`: the small frame the answer was about (no markers on it). `points`: centres in
        small-frame px. `ring`: radius our marker covers. `label_boxes`: each label's rectangle
        relative to its centre (dx, dy, w, h), also covered on later frames."""
        self.pw, self.ph = patch
        self.ring = ring
        self.targets: list[Target] = []
        for i, (x, y, label) in enumerate(points):
            p = self._cut(first, x, y)
            box = label_boxes[i] if label_boxes else (0.0, 0.0, 0.0, 0.0)
            trackable = p is not None and float(p.std()) >= MIN_CONTRAST
            self.targets.append(Target(p, x, y, label, box, True, trackable))

    def _cut(self, frame: np.ndarray, x: float, y: float) -> np.ndarray | None:
        top, left = round(y - self.ph / 2), round(x - self.pw / 2)
        if top < 0 or left < 0 or top + self.ph > frame.shape[0] or left + self.pw > frame.shape[1]:
            return None
        return frame[top : top + self.ph, left : left + self.pw].copy()

    def _mask(self, t: Target, occluders=()) -> np.ndarray:
        """True where the live frame shows content, not something of ours: the marker's ring and
        label, and our other windows (`occluders`: x, y, w, h in frame px, e.g. the answer bubble)."""
        yy, xx = np.mgrid[0 : self.ph, 0 : self.pw]
        cx, cy = self.pw / 2, self.ph / 2
        m = (xx - cx) ** 2 + (yy - cy) ** 2 > self.ring**2
        dx, dy, w, h = t.label_box
        if w and h:
            m &= ~((xx >= cx + dx) & (xx <= cx + dx + w) & (yy >= cy + dy) & (yy <= cy + dy + h))
        left, top = t.x - cx, t.y - cy  # the patch's corner in frame px
        for ox, oy, ow, oh in occluders:
            m &= ~((xx + left >= ox) & (xx + left < ox + ow) & (yy + top >= oy) & (yy + top < oy + oh))
        return m

    def update(self, frame: np.ndarray, occluders=()) -> list[Target]:
        """Check every target against a new small frame; positions and visibility are updated in place."""
        for t in self.targets:
            if not t.trackable:
                continue  # nothing distinctive to follow: leave it as it was
            if t.visible:
                here = self._cut(frame, t.x, t.y)
                if here is not None and _ncc_masked(t.patch, here, self._mask(t, occluders)) >= STAY:
                    t.misses = 0
                    continue
            score, top, left = match(frame, t.patch)
            x, y = left + self.pw / 2, top + self.ph / 2
            # The best match is the marker's own spot, only scored lower because our ring sits on it.
            on_itself = t.visible and abs(x - t.x) <= 2 and abs(y - t.y) <= 2 and score >= FOUND / 2
            if score >= FOUND or on_itself:
                t.x, t.y, t.visible, t.misses = x, y, True, 0
            else:
                t.misses += 1
                if t.misses >= 2:
                    t.visible = False
        return self.targets
