"""Markers follow what they point at: still there, scrolled, gone, back again."""

import numpy as np
import pytest

from marginalia.tracking import Tracker, match, to_small_gray

H, W = 300, 480


def page(seed=1, h=H * 3, w=W):
    """A tall 'document': random text-like blobs on white, so every region is distinctive."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w), 245.0, np.float32)
    for _ in range(h * w // 400):
        y, x = rng.integers(0, h - 4), rng.integers(0, w - 12)
        img[y : y + rng.integers(2, 5), x : x + rng.integers(3, 12)] = rng.uniform(20, 90)
    return img


def view(doc, scroll=0):
    return doc[scroll : scroll + H].copy()


def draw_marker(frame, x, y, r=8):
    """What our overlay adds on top of the screen: an amber ring (bright) around the target."""
    yy, xx = np.mgrid[0 : frame.shape[0], 0 : frame.shape[1]]
    ring = np.abs(np.hypot(xx - x, yy - y) - r) < 1.5
    out = frame.copy()
    out[ring] = 180.0
    return out


@pytest.fixture
def doc():
    return page()


def test_match_finds_a_patch_where_it_is(doc):
    frame = view(doc)
    patch = frame[100:122, 200:264]
    score, top, left = match(frame, patch)
    assert score > 0.99 and (top, left) == (100, 200)


def test_still_there_with_our_marker_drawn_on_it(doc):
    t = Tracker(view(doc), [(232, 111, "eq 4")])
    [target] = t.update(draw_marker(view(doc), 232, 111))
    assert target.visible and (target.x, target.y) == (232, 111)


def test_scrolling_moves_the_marker_with_the_content(doc):
    t = Tracker(view(doc, 120), [(232, 211, "eq 4")])
    [target] = t.update(draw_marker(view(doc, 160), 232, 211))  # scrolled down 40 px
    assert target.visible and target.x == pytest.approx(232, abs=1) and target.y == pytest.approx(171, abs=1)


def test_content_gone_hides_the_marker_and_its_return_shows_it(doc):
    t = Tracker(view(doc, 120), [(232, 211, "eq 4")])
    other = page(seed=99)[:H]  # another app, another desktop
    assert not t.update(other)[0].visible
    [back] = t.update(view(doc, 120))
    assert back.visible and (back.x, back.y) == pytest.approx((232, 211), abs=1)


def test_scrolled_out_of_view_is_gone_not_misplaced(doc):
    t = Tracker(view(doc, 0), [(232, 30, "title")])
    assert not t.update(view(doc, 200))[0].visible


def test_a_blank_spot_is_left_alone():
    blank = np.full((H, W), 245.0, np.float32)
    t = Tracker(blank, [(100, 100, "margin")])
    [target] = t.update(page()[:H])
    assert not target.trackable and target.visible, "nothing distinctive: don't guess"


def test_the_label_is_ignored_too(doc):
    t = Tracker(view(doc), [(232, 111, "eq 4")], label_boxes=[(4, -11, 28, 8)])
    frame = view(doc)
    frame[100:108, 236:264] = 30.0  # the label pill drawn over the top-right of the patch
    assert t.update(frame)[0].visible


def test_to_small_gray():
    rgb = np.zeros((900, 1440, 3), np.uint8)
    rgb[:, :, 0] = 255
    g = to_small_gray(rgb)
    assert g.shape == (300, 480) and g.mean() == pytest.approx(0.299 * 255, abs=0.5)
