"""OCR post-processing with a fake engine: both RapidOCR output shapes, scaling, order, filtering."""
from types import SimpleNamespace

import pytest
from PIL import Image

from marginalia.ocr import OCR


def quad(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def ocr_with(kind, engine):
    """An OCR whose only loader returns `engine`, so no real model is imported."""
    return OCR(loaders=[(kind, lambda: engine)]) if engine else OCR(loaders=[])


RAW = [
    (quad(500, 100, 700, 120), "second on line 1", 0.9),
    (quad(10, 102, 200, 122), "first on line 1", 0.95),
    (quad(10, 300, 300, 320), "line 2", 0.8),
    (quad(10, 400, 300, 420), "garbage", 0.2),
    (quad(10, 500, 300, 520), "   ", 0.99),
]


def v1_engine(arr):
    return RAW, 0.01


def v2_engine(arr):
    boxes, txts, scores = zip(*RAW, strict=True)
    return SimpleNamespace(boxes=list(boxes), txts=list(txts), scores=list(scores))


@pytest.mark.parametrize(("kind", "engine"), [("v1", v1_engine), ("v2", v2_engine)])
def test_lines_in_reading_order_with_low_scores_and_blanks_dropped(kind, engine):
    lines = ocr_with(kind, engine).read(Image.new("RGB", (1000, 800)))
    assert [l.text for l in lines] == ["first on line 1", "second on line 1", "line 2"]
    assert [l.id for l in lines] == [0, 1, 2]
    assert lines[0].box == (10, 102, 200, 122)


def test_big_screens_are_downscaled_for_ocr_and_boxes_scaled_back():
    seen = {}

    def engine(arr):
        seen["shape"] = arr.shape
        return [(quad(100, 100, 200, 110), "x", 0.9)], 0

    [line] = ocr_with("v1", engine).read(Image.new("RGB", (4400, 2000)), max_edge=2200)
    assert seen["shape"][:2] == (1000, 2200)
    assert line.box == pytest.approx((200, 200, 400, 220))


def test_missing_engine_returns_nothing():
    o = ocr_with(None, None)
    assert not o.available and o.read(Image.new("RGB", (10, 10))) == []


# loading the engine -----------------------------------------------------------------------


def _fails(exc):
    def load():
        raise exc

    return load


def test_first_engine_that_loads_wins():
    o = OCR(loaders=[("v1", lambda: "engine-1"), ("v2", lambda: "engine-2")])
    assert (o.engine, o.kind, o.available) == ("engine-1", "v1", True)


def test_falls_back_to_the_newer_package():
    o = OCR(loaders=[("v1", _fails(ImportError("no rapidocr_onnxruntime"))), ("v2", lambda: "engine-2")])
    assert (o.engine, o.kind) == ("engine-2", "v2")


def test_no_engine_keeps_the_reason():
    o = OCR(loaders=[("v1", _fails(ImportError("a"))), ("v2", _fails(OSError("onnxruntime broken")))])
    assert not o.available and isinstance(o.error, OSError)
