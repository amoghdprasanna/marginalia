"""Turning model points into screen positions, and keeping the bubble off what it points at."""

import pytest
from helpers import make_snapshot

from marginalia.brain import Point
from marginalia.capture import prepare
from marginalia.ocr import TextLine
from marginalia.pointing import MERGE_RADIUS, keep_on_screen, place_box, resolve_points


@pytest.fixture
def scene():
    snap = make_snapshot(logical=(1440, 900), dpr=2.0, cursor=(700, 450))
    return snap, prepare(snap)


def full_xy(prep, lx, ly):
    """The full-image pixel the model would name for logical point (lx, ly) on a 2x screen."""
    return prep.physical_to_full(lx * 2, ly * 2)


def test_full_image_point_lands_on_its_logical_spot(scene):
    snap, prep = scene
    x, y = full_xy(prep, 300, 200)
    [(lx, ly, label)] = resolve_points(prep, snap, [], [Point("full", x, y, None, "eq")])
    assert lx == pytest.approx(300, abs=2) and ly == pytest.approx(200, abs=2) and label == "eq"


def test_zoom_point_is_more_precise_than_full(scene):
    snap, prep = scene
    [(lx, ly, _)] = resolve_points(prep, snap, [], [Point("zoom", *prep.cursor_zoom, None, "c")])
    assert lx == pytest.approx(700, abs=1) and ly == pytest.approx(450, abs=1)


def test_point_near_its_ocr_line_snaps_onto_the_line(scene):
    snap, prep = scene
    line = TextLine(7, "H = -J Σ Z_i Z_j", (400, 600, 1000, 640), 0.95)  # physical px
    x, y = full_xy(prep, 350, 318)  # a few px below the line's middle (logical y 310)
    [(lx, ly, _)] = resolve_points(prep, snap, [line], [Point("full", x, y, 7, "H")])
    assert ly == pytest.approx(310, abs=0.5)
    assert lx == pytest.approx(350, abs=2)  # x kept: it may point at one symbol in the line


def test_point_far_from_its_line_trusts_the_text(scene):
    snap, prep = scene
    line = TextLine(2, "theorem 1", (200, 100, 600, 140), 0.95)
    x, y = full_xy(prep, 1200, 800)
    [(lx, ly, _)] = resolve_points(prep, snap, [line], [Point("full", x, y, 2, "thm")])
    assert (lx, ly) == pytest.approx((200, 60))


def test_line_id_alone_is_enough(scene):
    snap, prep = scene
    line = TextLine(0, "abc", (100, 100, 300, 120), 0.9)
    [(lx, ly, _)] = resolve_points(prep, snap, [line], [Point("full", None, None, 0, "abc")])
    assert (lx, ly) == pytest.approx((100, 55))


def test_unusable_points_are_skipped(scene):
    snap, prep = scene
    assert resolve_points(prep, snap, [], [Point("full", None, None, 99, "ghost")]) == []


def test_points_on_the_same_spot_merge_into_one_marker(scene):
    snap, prep = scene
    a = full_xy(prep, 500, 300)
    b = full_xy(prep, 500 + MERGE_RADIUS - 10, 300 + 10)
    out = resolve_points(prep, snap, [], [Point("full", *a, None, "one"), Point("full", *b, None, "two")])
    assert [label for *_, label in out] == ["one"]


def test_separate_targets_each_get_a_marker_up_to_the_cap(scene):
    snap, prep = scene
    pts = [Point("full", *full_xy(prep, 100 + i * 200, 300), None, str(i)) for i in range(6)]
    assert [label for *_, label in resolve_points(prep, snap, [], pts)] == ["0", "1", "2", "3"]


SCREEN = (0, 0, 1440, 900)


def inside(box, size, pt):
    (x, y), (w, h) = box, size
    return x <= pt[0] <= x + w and y <= pt[1] <= y + h


@pytest.mark.parametrize("cursor", [(700, 450), (5, 5), (1435, 895), (1435, 5)])
def test_box_stays_on_screen_and_off_the_cursor(cursor):
    size = (440, 260)
    x, y = place_box(size, SCREEN, cursor, [])
    assert 0 <= x and x + size[0] <= 1440 and 0 <= y and y + size[1] <= 900
    assert not inside((x, y), size, cursor)


def test_box_avoids_a_target_when_there_is_room():
    size = (440, 260)
    cursor = (500, 300)
    target = (cursor[0] + 200, cursor[1] + 120)  # where the default spot would put the box
    x, y = place_box(size, SCREEN, cursor, [target])
    assert not inside((x, y), size, target)


def test_keep_on_screen_leaves_a_visible_box_alone():
    assert keep_on_screen((100, 100), (48, 48), [(0, 0, 1440, 900)]) == (100, 100)


def test_keep_on_screen_pulls_a_box_back_onto_the_nearest_screen():
    screens = [(0, 0, 1440, 900), (1440, 0, 1920, 1080)]
    assert keep_on_screen((5000, 40), (48, 48), screens) == (1440 + 1920 - 48, 40)
    assert keep_on_screen((-300, -300), (48, 48), screens) == (0, 0)
