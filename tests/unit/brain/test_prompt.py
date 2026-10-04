"""What we send: OCR line selection near the cursor and the per-question text."""

from helpers import make_snapshot

from marginalia.brain import (
    MAX_HISTORY_CHARS,
    build_user_text,
    select_lines,
)
from marginalia.capture import prepare
from marginalia.ocr import TextLine


def _line(i, y, x=100, text="t"):
    return TextLine(i, text, (x, y, x + 200, y + 20), 0.9)


def test_select_lines_keeps_everything_under_the_limit():
    prep = prepare(make_snapshot())
    lines = [_line(i, i * 30) for i in range(5)]
    assert select_lines(lines, prep, limit=10) == lines


def test_select_lines_keeps_the_lines_nearest_the_cursor_in_reading_order():
    snap = make_snapshot(cursor=(700, 450))  # physical (1400, 900)
    prep = prepare(snap)
    lines = [_line(i, i * 100, x=1300) for i in range(18)]
    kept = select_lines(lines, prep, limit=3)
    assert [l.id for l in kept] == [8, 9, 10]


def test_user_text_lists_ocr_in_full_image_pixels_and_trims_history():
    prep = prepare(make_snapshot())
    sx, sy = prep.full_scale
    line = TextLine(0, "d = 2t + 1", (100 * sx, 50 * sy, 300 * sx, 70 * sy), 0.99)
    text = build_user_text(prep, [line], "why odd?", [("q1", "A" * (MAX_HISTORY_CHARS + 500))])
    assert "[0] [100, 50, 300, 70] d = 2t + 1" in text
    assert text.rstrip().endswith("Question: why odd?")
    assert "A" * MAX_HISTORY_CHARS in text and "A" * (MAX_HISTORY_CHARS + 1) not in text


def test_user_text_says_when_ocr_is_missing():
    assert "OCR: not available" in build_user_text(prepare(make_snapshot()), [], "q", [])
