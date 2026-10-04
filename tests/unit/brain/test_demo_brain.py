"""Demo mode: canned answers that still point and stream, for trying the UI without a key."""

from marginalia.brain import (
    DemoBrain,
)


def test_demo_brain_points_once_at_the_cursor(prep):
    a = DemoBrain(delay=0).ask(prep, [], "q", [])
    assert len(a.points) == 1
    assert (a.points[0].x, a.points[0].y) == prep.cursor_zoom


def test_demo_brain_streams_too(prep):
    seen = []
    a = DemoBrain(delay=0).ask(prep, [], "q", [], on_text=seen.append)
    assert seen and seen[-1].strip() == a.text.strip()
