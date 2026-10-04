"""The model boundary: what we send, and how forgivingly we read what comes back."""

import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from helpers import fake_client, make_snapshot

from marginalia.brain import (
    ANSWER_SCHEMA,
    MAX_HISTORY_CHARS,
    MAX_LABEL,
    BrainError,
    Cancelled,
    ClaudeBrain,
    DemoBrain,
    build_user_text,
    parse_reply,
    partial_answer,
    select_lines,
)
from marginalia.capture import prepare
from marginalia.ocr import TextLine

# parse_reply -------------------------------------------------------------------------------
# The API enforces ANSWER_SCHEMA, so replies are valid JSON; what's left to handle is a reply that
# was cut off, and keeping the UI's limits (4 points, short labels) that the schema can't express.


def _reply(answer="ok", points=()):
    return json.dumps({"answer": answer, "points": list(points)})


def _pt(**kw):
    return {"image": "full", "x": 10, "y": 20, "line": None, "label": "eq 4", **kw}


def test_parses_the_envelope():
    a = parse_reply(_reply("**Yes.**", [_pt(line=3)]))
    assert a.text == "**Yes.**"
    p = a.points[0]
    assert (p.image, p.x, p.y, p.line, p.label) == ("full", 10.0, 20.0, 3, "eq 4")


def test_latex_survives_because_the_api_escapes_it():
    """The old lenient parser repaired "\beta" by hand; with structured outputs it arrives escaped."""
    assert parse_reply(_reply(r"\beta and \rho")).text == r"\beta and \rho"


def test_keeps_at_most_four_points():
    a = parse_reply(_reply(points=[_pt(x=i) for i in range(7)]))
    assert [p.x for p in a.points] == [0, 1, 2, 3]


def test_labels_get_a_default_and_a_length_limit():
    a = parse_reply(_reply(points=[_pt(label="  "), _pt(label="L" * 80), _pt(image="zoom")]))
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


# partial_answer: decoding the answer while it streams ---------------------------------------


def test_partial_answer_is_none_until_the_key_arrives():
    assert partial_answer("") is None
    assert partial_answer('{"ans') is None


def test_partial_answer_grows_with_the_stream():
    raw = _reply("Line one.\nIt's \"quoted\" ⊗ |ψ⟩")
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


# select_lines / build_user_text ------------------------------------------------------------


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


# ClaudeBrain --------------------------------------------------------------------------------


@pytest.fixture
def prep():
    return prepare(make_snapshot())


def test_request_shape(cfg, prep):
    client, messages = fake_client()
    ClaudeBrain(cfg, client=client).ask(prep, [], "what is d?", [])
    req = messages.requests[0]
    assert req["model"] == "claude-opus-5"
    assert req["max_tokens"] == 16000
    assert req["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": ANSWER_SCHEMA}}
    assert req["fallbacks"] == "default" and req["betas"] == [ClaudeBrain.FALLBACK_BETA]
    [system] = req["system"]
    assert "quantum error correction" in system["text"]
    assert system["cache_control"] == {"type": "ephemeral"}, "the fixed system prompt is cached"
    content = req["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "image", "text"]
    assert all(set(b) == {"type", "source"} for b in content[:2]), "no undocumented fields on image blocks"


def test_reads_only_text_blocks(cfg, prep):
    blocks = [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text='{"answer": "two", "points": []}'),
    ]
    client, _ = fake_client(blocks=blocks)
    assert ClaudeBrain(cfg, client=client).ask(prep, [], "q", []).text == "two"


def test_refusal_becomes_a_friendly_error(cfg, prep):
    client, _ = fake_client(stop_reason="refusal", blocks=[])
    with pytest.raises(BrainError, match="declined"):
        ClaudeBrain(cfg, client=client).ask(prep, [], "q", [])


def test_truncated_answer_says_so(cfg, prep):
    client, _ = fake_client(stop_reason="max_tokens")
    assert "length limit" in ClaudeBrain(cfg, client=client).ask(prep, [], "q", []).text


def test_missing_key_explains_how_to_fix(cfg, prep):
    cfg.api_key = None
    with pytest.raises(BrainError, match="ANTHROPIC_API_KEY"):
        ClaudeBrain(cfg).ask(prep, [], "q", [])


_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status(cls, code, msg="boom"):
    return cls(msg, response=httpx2.Response(code, request=_REQ), body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status(anthropic.AuthenticationError, 401), "key was rejected"),
        (_status(anthropic.NotFoundError, 404), "was not found"),
        (_status(anthropic.RateLimitError, 429), "Rate limited"),
        (_status(anthropic.BadRequestError, 400, "image exceeds max size"), "screenshot size"),
        (_status(anthropic.BadRequestError, 400, "messages: bad"), "rejected the request"),
        (_status(anthropic.InternalServerError, 500), "API error 500"),
        (anthropic.APIConnectionError(request=_REQ), "internet connection"),
    ],
)
def test_api_errors_become_actionable_messages(cfg, prep, error, expected):
    client, _ = fake_client(error=error)
    with pytest.raises(BrainError, match=expected):
        ClaudeBrain(cfg, client=client).ask(prep, [], "q", [])


def test_demo_brain_points_once_at_the_cursor(prep):
    a = DemoBrain(delay=0).ask(prep, [], "q", [])
    assert len(a.points) == 1
    assert (a.points[0].x, a.points[0].y) == prep.cursor_zoom


def test_usage_is_reported_for_cost_tracking(cfg, prep):
    client, messages = fake_client()
    messages.response.usage = SimpleNamespace(
        input_tokens=3100, output_tokens=240, cache_read_input_tokens=700, cache_creation_input_tokens=None
    )
    u = ClaudeBrain(cfg, client=client).ask(prep, [], "q", []).usage
    assert (u.input_tokens, u.output_tokens, u.cache_read, u.cache_write) == (3100, 240, 700, 0)


# streaming -----------------------------------------------------------------------------------


def test_answer_streams_to_on_text_as_it_grows(cfg, prep):
    reply = _reply("The code distance: d = 2t + 1.", [_pt()])
    client, _ = fake_client(text=reply)
    seen = []
    a = ClaudeBrain(cfg, client=client).ask(prep, [], "q", [], on_text=seen.append)
    assert seen[-1] == "The code distance: d = 2t + 1."
    assert len(seen) > 2 and all(b.startswith(a) for a, b in zip(seen, seen[1:], strict=False))
    assert a.text == seen[-1] and len(a.points) == 1
    assert a.first_text is not None and a.first_text <= a.elapsed


def test_cancelling_closes_the_stream_early(cfg, prep):
    client, messages = fake_client(text=_reply("word " * 50))

    def stop(_text):
        raise Cancelled

    with pytest.raises(Cancelled):
        ClaudeBrain(cfg, client=client).ask(prep, [], "q", [], on_text=stop)
    stream = messages.streams[0]
    assert stream.closed and stream.read < len(stream.chunks)


def test_cut_off_stream_keeps_the_prose_and_says_so(cfg, prep):
    client, _ = fake_client(text='{"answer": "Because the syndrome', stop_reason="max_tokens")
    a = ClaudeBrain(cfg, client=client).ask(prep, [], "q", [])
    assert a.text.startswith("Because the syndrome") and "length limit" in a.text


def test_refusal_after_partial_text_is_still_an_error(cfg, prep):
    client, _ = fake_client(text='{"answer": "Sure, the', stop_reason="refusal")
    seen = []
    with pytest.raises(BrainError, match="declined"):
        ClaudeBrain(cfg, client=client).ask(prep, [], "q", [], on_text=seen.append)
    assert seen, "the partial was shown first; the controller replaces it with the error"


def test_demo_brain_streams_too(prep):
    seen = []
    a = DemoBrain(delay=0).ask(prep, [], "q", [], on_text=seen.append)
    assert seen and seen[-1].strip() == a.text.strip()
