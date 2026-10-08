"""ClaudeBrain against a fake client: request shape, streaming, cancelling, errors, usage."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from helpers import envelope, fake_client, point_dict

from marginalia.brain import (
    ANSWER_SCHEMA,
    BrainError,
    Cancelled,
    ClaudeBrain,
)

_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status(cls, code, msg="boom"):
    return cls(msg, response=httpx2.Response(code, request=_REQ), body=None)


def test_request_shape(cfg, prep):
    client, messages = fake_client()
    ClaudeBrain(cfg, client=client).ask(prep, [], "what is d?", [])
    req = messages.requests[0]
    assert req["model"] == "claude-opus-5-5"
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
    text = ClaudeBrain(cfg, client=client).ask(prep, [], "q", []).text
    assert "length limit" in text and "Settings" in text, "says where to fix it, not which env var"


def test_missing_key_points_to_settings(cfg, prep):
    cfg.api_key = None
    with pytest.raises(BrainError, match="Settings") as err:
        ClaudeBrain(cfg).ask(prep, [], "q", [])
    assert err.value.action == "settings"


@pytest.mark.parametrize(
    ("error", "expected", "action"),
    [
        (_status(anthropic.AuthenticationError, 401), "key was rejected", "settings"),
        (_status(anthropic.NotFoundError, 404), "isn't available", "settings"),
        (_status(anthropic.RateLimitError, 429), "Too many requests", "retry"),
        (_status(anthropic.BadRequestError, 400, "image exceeds max size"), "High-resolution", "settings"),
        (_status(anthropic.BadRequestError, 400, "messages: bad"), "couldn't process", None),
        (_status(anthropic.InternalServerError, 500), "having trouble", "retry"),
        (anthropic.APIConnectionError(request=_REQ), "internet connection", "retry"),
    ],
)
def test_api_errors_say_what_to_do_next(cfg, prep, error, expected, action):
    client, _ = fake_client(error=error)
    with pytest.raises(BrainError, match=expected) as err:
        ClaudeBrain(cfg, client=client).ask(prep, [], "q", [])
    assert err.value.action == action
    assert "MARGINALIA_" not in str(err.value) and ".env" not in str(err.value), "plain language, no env vars"


def test_usage_is_reported_for_cost_tracking(cfg, prep):
    client, messages = fake_client()
    messages.response.usage = SimpleNamespace(
        input_tokens=3100, output_tokens=240, cache_read_input_tokens=700, cache_creation_input_tokens=None
    )
    u = ClaudeBrain(cfg, client=client).ask(prep, [], "q", []).usage
    assert (u.input_tokens, u.output_tokens, u.cache_read, u.cache_write) == (3100, 240, 700, 0)


def test_answer_streams_to_on_text_as_it_grows(cfg, prep):
    reply = envelope("The code distance: d = 2t + 1.", [point_dict()])
    client, _ = fake_client(text=reply)
    seen = []
    a = ClaudeBrain(cfg, client=client).ask(prep, [], "q", [], on_text=seen.append)
    assert seen[-1] == "The code distance: d = 2t + 1."
    assert len(seen) > 2 and all(b.startswith(a) for a, b in zip(seen, seen[1:], strict=False))
    assert a.text == seen[-1] and len(a.points) == 1
    assert a.first_text is not None and a.first_text <= a.elapsed


def test_cancelling_closes_the_stream_early(cfg, prep):
    client, messages = fake_client(text=envelope("word " * 50))

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


def test_a_key_builds_a_real_client_without_calling_the_network(cfg):
    brain = ClaudeBrain(cfg)
    assert isinstance(brain.client, anthropic.Anthropic)


def test_an_error_in_the_middle_of_the_stream_is_explained(cfg, prep):
    client, messages = fake_client(text=envelope("word " * 20))
    messages.mid_error = anthropic.APIError("overloaded", _REQ, body=None)
    with pytest.raises(BrainError, match="interrupted"):
        ClaudeBrain(cfg, client=client).ask(prep, [], "q", [])
    assert messages.streams[0].closed
