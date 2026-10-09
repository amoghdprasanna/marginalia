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
TIE = 0.03  # a place elsewhere must beat the current spot by more than this to move the marker
KEEP = 0.5  # below this the current spot no longer counts as the same content
HOLD = 0.7  # at or above this the current spot still holds, however good a look-alike elsewhere is
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


def score_map(frame: np.ndarray, patch: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Normalised cross-correlation of `patch` at every placement in `frame` (indexed by top, left).

    With `mask` (True = use this pixel of the patch), every placement is scored on the same
    pixels. That matters: our marker sits on the current spot, so scoring the current spot with
    the ring ignored but a look-alike elsewhere with every pixel would favour the look-alike.
    FFT correlations plus local sums: O(N log N) for the whole frame.
    """
    fh, fw = frame.shape
    ph, pw = patch.shape
    if ph > fh or pw > fw:
        return np.zeros((1, 1), np.float32)
    m = np.ones_like(patch, np.float32) if mask is None else mask.astype(np.float32)
    n = float(m.sum())
    if n < 16:
        return np.zeros((fh - ph + 1, fw - pw + 1), np.float32)
    p = (patch - (patch * m).sum() / n) * m  # zero-mean over the used pixels, zero elsewhere
    p_norm = float(np.sqrt((p * p).sum()))
    shape = (fh + ph - 1, fw + pw - 1)
    f_hat, f2_hat = np.fft.rfft2(frame, shape), np.fft.rfft2(frame * frame, shape)

    def corr(kernel_hat):
        return np.fft.irfft2(kernel_hat, shape)[: fh - ph + 1, : fw - pw + 1]

    m_hat = np.conj(np.fft.rfft2(m, shape))
    num = corr(f_hat * np.conj(np.fft.rfft2(p, shape)))
    win_sum, win_sq = corr(f_hat * m_hat), corr(f2_hat * m_hat)
    var = np.maximum(win_sq - win_sum * win_sum / n, 1e-6)
    if p_norm < 1e-6:
        return np.zeros_like(var)
    score = num / (np.sqrt(var) * p_norm)
    score[var < (MIN_CONTRAST**2) * n * 0.25] = 0.0  # flat windows can't be a real match
    return score


def match(frame: np.ndarray, patch: np.ndarray, mask: np.ndarray | None = None, runner_up: bool = False):
    """Best placement of `patch` in `frame`: (score, top, left). With `runner_up`, also the best
    placement at least a patch away from it, which says how unique the best one is."""
    score = score_map(frame, patch, mask)
    i = int(np.argmax(score))
    top, left = divmod(i, score.shape[1])
    best = (float(score[top, left]), top, left)
    if not runner_up:
        return best
    ph, pw = patch.shape
    rest = score.copy()
    rest[max(0, top - ph) : top + ph, max(0, left - pw) : left + pw] = -1.0
    j = int(np.argmax(rest))
    t2, l2 = divmod(j, rest.shape[1])
    return best, (float(rest[t2, l2]), t2, l2)


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
    came_from: tuple[float, float] | None = None  # where it last moved from: never bounce straight back


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
            # Search with the marker's ring and label ignored at every placement, so the current spot
            # (under our marker) and a look-alike elsewhere are scored on the same pixels.
            scores = score_map(frame, t.patch, self._mask(t))
            i = int(np.argmax(scores))
            top, left = divmod(i, scores.shape[1])
            best = float(scores[top, left])
            cur_top, cur_left = round(t.y - self.ph / 2), round(t.x - self.pw / 2)
            here = -1.0
            if t.visible and 0 <= cur_top < scores.shape[0] and 0 <= cur_left < scores.shape[1]:
                here = float(scores[cur_top, cur_left])
            x, y = left + self.pw / 2, top + self.ph / 2
            back = t.came_from is not None and abs(x - t.came_from[0]) <= 3 and abs(y - t.came_from[1]) <= 3
            if here >= HOLD or here >= max(best - TIE, KEEP):
                # Still clearly here (a real move leaves the old spot far below this), or as good as
                # anywhere: a tie or a look-alike never moves a marker.
                t.misses = 0
            elif back and here >= KEEP:
                # Back to where it just came from while this spot still matches: two look-alikes,
                # and our own marker tipping the balance. Moving would start a back-and-forth.
                t.misses = 0
            elif best >= FOUND:
                if t.visible:
                    t.came_from = (t.x, t.y)
                t.x, t.y, t.visible, t.misses = x, y, True, 0
            else:
                t.misses += 1
                if t.misses >= 2:
                    t.visible = False
        return self.targets
