"""Turns the model's points into on-screen positions, and places the answer bubble."""
from __future__ import annotations

from .brain import Point
from .capture import Prepared, Snapshot
from .ocr import TextLine

MERGE_RADIUS = 48  # logical px; closer markers would draw as one ring split in two


def resolve_points(
    prep: Prepared, snap: Snapshot, lines: list[TextLine], points: list[Point], max_points: int = 4
) -> list[tuple[float, float, str]]:
    """Map model points to logical screen coordinates, snapping to OCR lines when they agree."""
    by_id = {l.id: l for l in lines}
    out: list[tuple[float, float, str]] = []
    for pt in points[:max_points]:
        px = py = None
        if pt.x is not None and pt.y is not None:
            px, py = prep.to_physical(pt.image, pt.x, pt.y)
        line = by_id.get(pt.line) if pt.line is not None else None
        if line is not None:
            x1, y1, x2, y2 = line.box
            margin = 0.6 * (y2 - y1) + 12
            mid_y = (y1 + y2) / 2
            if px is not None and x1 - margin <= px <= x2 + margin and y1 - margin <= py <= y2 + margin:
                px, py = min(max(px, x1), x2), mid_y  # keep the model's x, snap y onto the line
            else:
                px, py = (x1 + x2) / 2, mid_y  # coordinate disagrees with its own line id: trust the text
        if px is None:
            continue
        lx, ly = snap.physical_to_logical(px, py)
        if any(abs(lx - ox) < MERGE_RADIUS and abs(ly - oy) < MERGE_RADIUS for ox, oy, _ in out):
            continue
        out.append((lx, ly, pt.label))
    return out


def place_box(
    size: tuple[int, int],
    screen: tuple[int, int, int, int],
    cursor: tuple[float, float],
    avoid: list[tuple[float, float]],
    gap: int = 28,
    margin: int = 16,
) -> tuple[int, int]:
    """Pick a spot for a w x h box near the cursor that covers neither the cursor nor the targets."""
    w, h = size
    sx, sy, sw, sh = screen
    cx, cy = cursor
    candidates = [
        (cx + gap, cy + gap / 2),
        (cx - gap - w, cy + gap / 2),
        (cx + gap, cy - gap / 2 - h),
        (cx - gap - w, cy - gap / 2 - h),
        (sx + sw - w - margin, sy + margin + 40),
        (sx + sw - w - margin, sy + sh - h - margin - 40),
        (sx + margin, sy + sh - h - margin - 40),
    ]
    keep_clear = [(cx, cy)] + list(avoid)
    best, best_score = None, float("-inf")
    for x, y in candidates:
        x = min(max(x, sx + margin), sx + sw - w - margin)
        y = min(max(y, sy + margin), sy + sh - h - margin)
        clearance = min(
            ((max(x - px, 0, px - (x + w))) ** 2 + (max(y - py, 0, py - (y + h))) ** 2) ** 0.5
            for px, py in keep_clear
        )
        near = ((x + w / 2 - cx) ** 2 + (y + h / 2 - cy) ** 2) ** 0.5
        score = min(clearance, 60) * 10 - near * 0.2
        if score > best_score:
            best, best_score = (int(x), int(y)), score
    return best
