"""The model boundary: what we send, and how forgivingly we read what comes back."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from helpers import fake_client, make_snapshot

from marginalia.brain import (
    MAX_HISTORY_CHARS,
    BrainError,
    ClaudeBrain,
    DemoBrain,
    build_user_text,
    parse_reply,
    select_lines,
)
from marginalia.capture import prepare
from marginalia.ocr import TextLine

# parse_reply -------------------------------------------------------------------------------


def test_parses_plain_json():
    a = parse_reply(
        '{"answer": "**Yes.**", "points": [{"image": "full", "x": 10, "y": 20, "line": 3, "label": "eq 4"}]}'
    )
    assert a.text == "**Yes.**"
    assert len(a.points) == 1
    p = a.points[0]
    assert (p.image, p.x, p.y, p.line, p.label) == ("full", 10.0, 20.0, 3, "eq 4")


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{"answer": "ok", "points": []}\n```',
        'Sure, here it is:\n{"answer": "ok", "points": []}\nHope that helps',
        '{"answer": "ok"}',
    ],
)
def test_tolerates_fences_prose_and_missing_points(raw):
    a = parse_reply(raw)
    assert a.text == "ok" and a.points == []


def test_repairs_stray_latex_backslashes():
    a = parse_reply(r'{"answer": "the state \alpha|0⟩ + \beta|1⟩", "points": []}')
    assert a.text == r"the state \alpha|0⟩ + \beta|1⟩"


def test_non_json_reply_is_shown_as_is():
    a = parse_reply("I can't see the screen clearly.")
    assert a.text == "I can't see the screen clearly." and a.points == []


def test_empty_reply_gets_a_placeholder():
    assert "empty" in parse_reply("   ").text


def test_point_variants_are_normalised():
    a = parse_reply(
        '{"answer": "x", "points": ['
        '{"image": "Zoom image", "point": [5, 6], "label": "a"},'
        '{"x": "7.5", "y": " 8 ", "label": ""},'
        '{"line": 4.0, "label": "' + "L" * 80 + '"},'
        '{"x": true, "y": 3},'
        '{"label": "nowhere"},'
        '"not a dict"'
        "]}"
    )
    assert [(p.image, p.x, p.y, p.line) for p in a.points] == [
        ("zoom", 5.0, 6.0, None),
        ("full", 7.5, 8.0, None),
        ("full", None, None, 4),
    ]
    assert a.points[1].label == "here"  # blank label gets a default
    assert len(a.points[2].label) == 48  # long label is cut


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
    assert req["output_config"] == {"effort": "medium"}
    assert req["fallbacks"] == "default" and req["betas"] == [ClaudeBrain.FALLBACK_BETA]
    assert "quantum error correction" in req["system"]
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


@pytest.mark.parametrize("cmd", [r"\beta", r"\frac", r"\rho", r"\theta", r"\nu", r"\otimes", r"\langle"])
def test_latex_that_collides_with_json_escapes_survives(cmd):
    assert parse_reply('{"answer": "' + cmd.replace("\\", "\\") + ' here", "points": []}').text == cmd + " here"


def test_real_newlines_before_words_stay_newlines():
    assert parse_reply(r'{"answer": "First.\nThen\ttab", "points": []}').text == "First.\nThen\ttab"


def test_correctly_escaped_latex_is_untouched():
    assert parse_reply(r'{"answer": "\\beta and \\rho", "points": []}').text == r"\beta and \rho"
