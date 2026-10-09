"""Markers follow what they point at: scrolled content takes its marker along, gone content hides it."""

import numpy as np
import pytest
from helpers import FakeBrain, ask_typed, build
from PIL import Image

from marginalia.brain import Point
from marginalia.capture import Snapshot, small_frame


def textured(seed=3, size=(1440, 2700)):
    """A long logical-size 'document' of text-like blobs, so every spot is distinctive."""
    rng = np.random.default_rng(seed)
    w, h = size
    small = np.full((h // 3, w // 3), 245, np.uint8)
    for _ in range(small.size // 300):
        y, x = rng.integers(0, small.shape[0] - 4), rng.integers(0, small.shape[1] - 12)
        small[y : y + rng.integers(2, 5), x : x + rng.integers(3, 12)] = rng.integers(20, 90)
    return Image.fromarray(small).convert("RGB").resize((w * 2, h * 2), Image.NEAREST)  # a 2x Retina page


class Screen:
    """What the fake screen shows: a window onto the document, scrolled by `scroll` logical px."""

    def __init__(self):
        self.doc = textured()
        self.scroll = 300
        self.other = None

    def image(self):
        if self.other is not None:
            return self.other
        top = self.scroll * 2
        return self.doc.crop((0, top, 2880, top + 1800))

    def grab(self, x, y):
        return Snapshot(self.image(), (0, 0, 1440, 900), (x, y))

    def frame(self, geo, width):
        return small_frame(self.image(), width)


@pytest.fixture
def screen():
    return Screen()


@pytest.fixture
def tracked(qtbot, cfg, screen):
    c = build(
        qtbot,
        cfg,
        brain=FakeBrain(points=[Point("full", 700, 400, None, "eq 4")]),
        grab=screen.grab,
        frame=screen.frame,
    )
    c.overlay.TRAVEL = c.overlay.PULSE = 0.01  # land at once
    c._track_timer.setInterval(30)
    ask_typed(qtbot, c, "what is this?")
    qtbot.waitUntil(c._track_timer.isActive, timeout=2000)
    yield c
    c.stop()


def marker(c):
    (p, _label), = c.overlay.targets
    return p.x(), p.y()


def test_scrolling_takes_the_marker_with_the_content(qtbot, tracked, screen):
    x0, y0 = marker(tracked)
    screen.scroll += 120  # the page scrolls up by 120 points
    qtbot.waitUntil(lambda: abs(marker(tracked)[1] - (y0 - 120)) < 6, timeout=3000)
    assert abs(marker(tracked)[0] - x0) < 6 and 0 not in tracked.overlay.hidden


def test_switching_away_hides_the_marker_and_coming_back_shows_it(qtbot, tracked, screen):
    screen.other = textured(seed=42).crop((0, 0, 2880, 1800))  # another app, another desktop
    qtbot.waitUntil(lambda: 0 in tracked.overlay.hidden, timeout=3000)
    screen.other = None
    qtbot.waitUntil(lambda: 0 not in tracked.overlay.hidden, timeout=3000)


def test_show_again_uses_where_things_are_now(qtbot, tracked, screen):
    y0 = tracked._last_pointing[2][0][1]
    screen.scroll += 90
    qtbot.waitUntil(lambda: abs(tracked._last_pointing[2][0][1] - (y0 - 90)) < 6, timeout=3000)
    tracked.bubble.replay_btn.click()
    assert abs(marker(tracked)[1] - (y0 - 90)) < 6, "the replayed marker flies to the content's new place"


def test_tracking_stops_when_the_thread_ends_or_a_new_question_starts(qtbot, tracked):
    tracked.bubble.dismiss()
    assert tracked.tracker is None and not tracked._track_timer.isActive()


def test_no_frame_grabber_means_no_tracking(qtbot, cfg, screen):
    c = build(qtbot, cfg, brain=FakeBrain(points=[Point("full", 700, 400, None, "eq 4")]), grab=screen.grab)
    ask_typed(qtbot, c, "q")
    assert c.tracker is None
