"""Coordinate fidelity: everything the model points at must land on the right screen pixel."""

import base64
import io
import math

import pytest
from helpers import make_snapshot
from PIL import Image

from marginalia.capture import (
    HIRES_TIER,
    RING_RGB,
    STANDARD_TIER,
    count_image_tokens,
    prepare,
    resized_size,
    to_b64_png,
)


def fits(w, h, max_edge, max_tokens):
    return (
        math.ceil(w / 28) * 28 <= max_edge
        and math.ceil(h / 28) * 28 <= max_edge
        and count_image_tokens(w, h) <= max_tokens
    )


def test_count_image_tokens_is_28px_patches():
    assert count_image_tokens(28, 28) == 1
    assert count_image_tokens(29, 28) == 2
    assert count_image_tokens(560, 280) == 20 * 10


def test_small_image_is_left_alone():
    assert resized_size(800, 600) == (800, 600)


@pytest.mark.parametrize("size", [(2880, 1800), (3840, 2160), (5120, 1440), (1800, 2880)])
@pytest.mark.parametrize("tier", [STANDARD_TIER, HIRES_TIER])
def test_resized_size_fits_the_tier_and_is_as_large_as_possible(size, tier):
    w, h = resized_size(*size, *tier)
    assert fits(w, h, *tier)
    assert not fits(w + 1, max(round((w + 1) * size[1] / size[0]), 1), *tier)  # one px wider would not fit


@pytest.mark.parametrize("size", [(2880, 1800), (3840, 2160), (1800, 2880)])
def test_resized_size_keeps_aspect_ratio(size):
    w, h = resized_size(*size)
    assert w / h == pytest.approx(size[0] / size[1], rel=0.01)


def test_portrait_is_the_transpose_of_landscape():
    w, h = resized_size(2880, 1800)
    assert resized_size(1800, 2880) == (h, w)


def test_snapshot_maps_between_logical_and_physical_on_a_secondary_screen():
    snap = make_snapshot(logical=(1440, 900), dpr=2.0, origin=(-1440, 0), cursor=(-720, 450))
    assert snap.cursor_physical == (1440.0, 900.0)
    assert snap.physical_to_logical(1440, 900) == (-720.0, 450.0)


@pytest.mark.parametrize("cursor", [(700, 450), (5, 5), (1435, 895), (0, 899)])
def test_prepare_round_trips_the_cursor_through_both_images(cursor):
    snap = make_snapshot(cursor=cursor)
    prep = prepare(snap)
    cpx, cpy = snap.cursor_physical
    for image, (x, y) in (("full", prep.cursor_full), ("zoom", prep.cursor_zoom)):
        px, py = prep.to_physical(image, x, y)
        tol = 2 * max(prep.full_scale) if image == "full" else 2 * max(prep.zoom_scale)
        assert abs(px - cpx) <= tol and abs(py - cpy) <= tol, image


def test_prepare_sends_images_at_the_exact_api_size():
    snap = make_snapshot(logical=(1440, 900), dpr=2.0)
    prep = prepare(snap)
    assert prep.full.size == resized_size(2880, 1800, *STANDARD_TIER)
    assert fits(*prep.zoom.size, *STANDARD_TIER)


def test_hires_sends_a_larger_full_image():
    snap = make_snapshot(logical=(1440, 900), dpr=2.0)
    assert prepare(snap, hires=True).full.width > prepare(snap).full.width


def test_zoom_crop_stays_inside_the_screen_near_edges():
    snap = make_snapshot(cursor=(2, 2))
    prep = prepare(snap)
    x0, y0 = prep.zoom_origin
    assert x0 >= 0 and y0 >= 0
    w, h = snap.image.size
    assert x0 + prep.zoom.width * prep.zoom_scale[0] <= w + 1
    assert y0 + prep.zoom.height * prep.zoom_scale[1] <= h + 1


def test_to_physical_clamps_points_outside_the_image():
    prep = prepare(make_snapshot())
    assert prep.to_physical("full", -50, -50) == (0, 0)
    fx, fy = prep.to_physical("full", 10**6, 10**6)
    assert fx == pytest.approx(prep.full.width * prep.full_scale[0])
    assert fy == pytest.approx(prep.full.height * prep.full_scale[1])


def test_physical_to_full_inverts_to_physical():
    prep = prepare(make_snapshot())
    assert prep.physical_to_full(*prep.to_physical("full", 300, 200)) == (300, 200)


def test_cursor_ring_is_drawn_without_touching_the_source():
    snap = make_snapshot(color=(255, 255, 255))
    prep = prepare(snap)
    assert RING_RGB in {c for _, c in prep.zoom.getcolors(1 << 16)}
    assert snap.image.getcolors() == [(snap.image.width * snap.image.height, (255, 255, 255))]


def test_to_b64_png_round_trips():
    img = Image.new("RGB", (4, 3), (1, 2, 3))
    back = Image.open(io.BytesIO(base64.standard_b64decode(to_b64_png(img))))
    assert back.format == "PNG" and back.size == (4, 3) and back.getpixel((0, 0)) == (1, 2, 3)


# Qt image conversion ---------------------------------------------------------------------


def test_qimage_converts_to_pil_with_exact_pixels():
    """Odd widths have padded rows in Qt; a wrong stride would shear the picture."""
    from PySide6.QtGui import QColor, QImage

    from marginalia.capture import qimage_to_pil

    q = QImage(5, 3, QImage.Format_RGB32)
    q.fill(QColor(10, 20, 30))
    q.setPixelColor(4, 2, QColor(255, 178, 36))
    img = qimage_to_pil(q)
    assert img.mode == "RGB" and img.size == (5, 3)
    assert img.getpixel((0, 0)) == (10, 20, 30)
    assert img.getpixel((4, 2)) == (255, 178, 36)
