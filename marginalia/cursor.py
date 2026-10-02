"""Where the mouse last *rested* on content. The orb asks about that spot, not about the orb itself."""
from __future__ import annotations


class RestTracker:
    """Pure: feed it (time, x, y) samples; `rest` is the last point the cursor held still at."""

    def __init__(self, start: tuple[int, int], now: float, jitter_px: int = 12, dwell_s: float = 0.45) -> None:
        self.jitter_px = jitter_px
        self.dwell_s = dwell_s
        self.rest = start
        self._anchor = start
        self._since = now

    def feed(self, now: float, pos: tuple[int, int]) -> None:
        moved = abs(pos[0] - self._anchor[0]) + abs(pos[1] - self._anchor[1])
        if moved > self.jitter_px:
            self._anchor, self._since = pos, now
        elif now - self._since >= self.dwell_s:
            self.rest = pos
