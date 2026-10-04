"""Reading the model's reply: the schema-checked envelope, cut-off replies, and the answer while it streams."""

import pytest
from helpers import envelope, point_dict

from marginalia.brain import (
    MAX_LABEL,
    parse_reply,
    partial_answer,
)


def test_parses_the_envelope():
    a = parse_reply(envelope("**Yes.**", [point_dict(line=3)]))
    assert a.text == "**Yes.**"
    p = a.points[0]
    assert (p.image, p.x, p.y, p.line, p.label) == ("full", 10.0, 20.0, 3, "eq 4")


def test_latex_survives_because_the_api_escapes_it():
    """The old lenient parser repaired "\beta" by hand; with structured outputs it arrives escaped."""
    assert parse_reply(envelope(r"\beta and \rho")).text == r"\beta and \rho"


def test_keeps_at_most_four_points():
    a = parse_reply(envelope(points=[point_dict(x=i) for i in range(7)]))
    assert [p.x for p in a.points] == [0, 1, 2, 3]


def test_labels_get_a_default_and_a_length_limit():
    a = parse_reply(envelope(points=[point_dict(label="  "), point_dict(label="L" * 80), point_dict(image="zoom")]))
    assert a.points[0].label == "here"
    assert len(a.points[1].label) == MAX_LABEL
    assert a.points[2].image == "zoom"


def test_cut_off_reply_shows_the_prose_that_arrived():
    a = parse_reply('{"answer": "The distance is d = 2t + 1, so', model="m")
    assert a.text == "The distance is d = 2t + 1, so" and a.points == []


def test_reply_without_an_envelope_is_shown_as_is():
    assert parse_reply("I can't see the screen clearly.").text == "I can't see the screen clearly."


def test_empty_reply_gets_a_placeholder():
    assert "empty" in parse_reply("   ").text


def test_partial_answer_is_none_until_the_key_arrives():
    assert partial_answer("") is None
    assert partial_answer('{"ans') is None


def test_partial_answer_grows_with_the_stream():
    raw = envelope("Line one.\nIt's \"quoted\" ⊗ |ψ⟩")
    seen = [partial_answer(raw[:i]) for i in range(len(raw) + 1)]
    texts = [t for t in seen if t is not None]
    assert texts[-1] == "Line one.\nIt's \"quoted\" ⊗ |ψ⟩"
    assert all(b.startswith(a) for a, b in zip(texts, texts[1:], strict=False)), "never shows text it later takes back"


@pytest.mark.parametrize("cut", range(1, 13))
def test_partial_answer_never_shows_half_an_escape(cut):
    escaped = r"é😀"  # é, then 😀 as a surrogate pair
    t = partial_answer('{"answer": "a' + escaped[:cut])
    assert t in {"a", "aé", "aé😀"} and "\\" not in t


def test_partial_answer_stops_at_the_closing_quote():
    assert partial_answer('{"answer": "done", "points": [{"label": "x"}]}') == "done"
