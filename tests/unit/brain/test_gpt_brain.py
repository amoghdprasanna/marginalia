"""GPTBrain against a fake client: request shape, streaming, cancelling, refusals, errors, usage."""

import sys
from dataclasses import replace
from types import SimpleNamespace

import httpx2
import openai
import pytest
from helpers import envelope, point_dict

from marginalia.brain import ANSWER_SCHEMA, BrainError, Cancelled, GPTBrain

_REQ = httpx2.Request("POST", "https://api.openai.com/v1/responses")


def _status(cls, code, msg="boom"):
    return cls(msg, response=httpx2.Response(code, request=_REQ), body=None)


class FakeStream:
    """What `client.responses.create(..., stream=True)` returns: events, as a context manager."""

    def __init__(self, events, error=None) -> None:
        self.events, self.error = events, error
        self.closed = False
        self.read = 0

    def __enter__(self):
        if self.error is not None:
            raise self.error
        return self

    def __exit__(self, *exc) -> None:
        self.closed = True

    def __iter__(self):
        for e in self.events:
            self.read += 1
            yield e


class FakeResponses:
    def __init__(self, text, status, reason, error, output, usage) -> None:
        self.text, self.status, self.reason, self.error = text, status, reason, error
        self.output, self.usage = output, usage
        self.requests: list[dict] = []
        self.streams: list[FakeStream] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        deltas = [
            SimpleNamespace(type="response.output_text.delta", delta=self.text[i : i + 7])
            for i in range(0, len(self.text), 7)
        ]
        resp = SimpleNamespace(
            status=self.status,
            output=self.output,
            incomplete_details=SimpleNamespace(reason=self.reason) if self.reason else None,
            usage=self.usage,
            model="gpt-6-astra-2026-09-01",
            error=SimpleNamespace(message="server exploded") if self.status == "failed" else None,
        )
        last = "response.completed" if self.status == "completed" else f"response.{self.status}"
        s = FakeStream([*deltas, SimpleNamespace(type=last, response=resp)], self.error)
        self.streams.append(s)
        return s


def fake_client(text=None, status="completed", reason=None, error=None, output=(), usage=None):
    text = envelope("hi") if text is None else text
    responses = FakeResponses(text, status, reason, error, list(output), usage)
    return SimpleNamespace(responses=responses), responses


@pytest.fixture
def gpt_cfg(cfg):
    return replace(cfg, provider="openai", model="gpt-6-astra")


def test_request_shape(gpt_cfg, prep):
    client, responses = fake_client()
    GPTBrain(gpt_cfg, client=client).ask(prep, [], "what is d?", [])
    req = responses.requests[0]
    assert req["stream"] is True and req["model"] == "gpt-6-astra"
    assert req["max_output_tokens"] == 16000 and req["reasoning"] == {"effort": "medium"}
    assert req["text"]["format"] == {"type": "json_schema", "name": "answer", "schema": ANSWER_SCHEMA, "strict": True}
    assert req["store"] is False, "screenshots are not kept on OpenAI's side"
    assert "quantum error correction" in req["instructions"]
    assert "integer pixel coordinates" in req["instructions"], "GPT answers in pixels, like Claude"
    content = req["input"][0]["content"]
    assert [b["type"] for b in content] == ["input_image", "input_image", "input_text"]
    assert all(b["detail"] == "original" for b in content[:2]), "no resizing, so coordinates line up"
    assert content[0]["image_url"].startswith("data:image/png;base64,")


def test_answer_streams_to_on_text_as_it_grows(gpt_cfg, prep):
    client, _ = fake_client(text=envelope("The code distance: d = 2t + 1.", [point_dict(x=40, y=60)]))
    seen = []
    a = GPTBrain(gpt_cfg, client=client).ask(prep, [], "q", [], on_text=seen.append)
    assert seen[-1] == a.text == "The code distance: d = 2t + 1." and len(seen) > 2
    assert (a.points[0].x, a.points[0].y) == (40, 60), "pixels pass straight through"
    assert a.model == "gpt-6-astra-2026-09-01" and a.first_text is not None


def test_cancelling_closes_the_stream_early(gpt_cfg, prep):
    client, responses = fake_client(text=envelope("word " * 50))

    def stop(_text):
        raise Cancelled

    with pytest.raises(Cancelled):
        GPTBrain(gpt_cfg, client=client).ask(prep, [], "q", [], on_text=stop)
    stream = responses.streams[0]
    assert stream.closed and stream.read < len(stream.events)


def test_cut_off_answer_keeps_the_prose_and_says_so(gpt_cfg, prep):
    client, _ = fake_client(text='{"answer": "Because the syndrome', status="incomplete", reason="max_output_tokens")
    a = GPTBrain(gpt_cfg, client=client).ask(prep, [], "q", [])
    assert a.text.startswith("Because the syndrome") and "length limit" in a.text


@pytest.mark.parametrize(
    "kw",
    [
        {"text": "", "output": [SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="no")])]},
        {"text": '{"answer": "Sure', "status": "incomplete", "reason": "content_filter"},
    ],
)
def test_a_refusal_is_a_friendly_error(gpt_cfg, prep, kw):
    client, _ = fake_client(**kw)
    with pytest.raises(BrainError, match="OpenAI declined"):
        GPTBrain(gpt_cfg, client=client).ask(prep, [], "q", [])


def test_a_failed_response_says_why(gpt_cfg, prep):
    client, _ = fake_client(status="failed")
    with pytest.raises(BrainError, match="server exploded"):
        GPTBrain(gpt_cfg, client=client).ask(prep, [], "q", [])


def test_a_stream_that_ends_without_a_response_is_interrupted(gpt_cfg, prep):
    client, responses = fake_client()
    real = responses.create

    def no_final(**kw):
        s = real(**kw)
        s.events = s.events[:-1]
        return s

    responses.create = no_final
    with pytest.raises(BrainError, match="interrupted") as err:
        GPTBrain(gpt_cfg, client=client).ask(prep, [], "q", [])
    assert err.value.action == "retry"


@pytest.mark.parametrize(
    ("error", "expected", "action"),
    [
        (_status(openai.AuthenticationError, 401), "key was rejected", "settings"),
        (_status(openai.NotFoundError, 404), "isn't available", "settings"),
        (_status(openai.RateLimitError, 429), "Too many requests", "retry"),
        (_status(openai.RateLimitError, 429, "insufficient_quota"), "out of credit", None),
        (_status(openai.BadRequestError, 400, "input: bad"), "OpenAI couldn't process", None),
        (_status(openai.InternalServerError, 500), "OpenAI is having trouble", "retry"),
        (openai.APIConnectionError(request=_REQ), "Couldn't reach OpenAI", "retry"),
    ],
)
def test_api_errors_say_what_to_do_next(gpt_cfg, prep, error, expected, action):
    client, _ = fake_client(error=error)
    with pytest.raises(BrainError, match=expected) as err:
        GPTBrain(gpt_cfg, client=client).ask(prep, [], "q", [])
    assert err.value.action == action


def test_usage_keeps_cached_tokens_apart(gpt_cfg, prep):
    details = SimpleNamespace(cached_tokens=700)
    usage = SimpleNamespace(input_tokens=3100, output_tokens=240, input_tokens_details=details)
    client, _ = fake_client(usage=usage)
    u = GPTBrain(gpt_cfg, client=client).ask(prep, [], "q", []).usage
    assert (u.input_tokens, u.output_tokens, u.cache_read, u.cache_write) == (2400, 240, 700, 0)


def test_missing_key_points_to_settings(gpt_cfg, prep):
    with pytest.raises(BrainError, match="OpenAI API key") as err:
        GPTBrain(replace(gpt_cfg, api_key=None)).ask(prep, [], "q", [])
    assert err.value.action == "settings"


def test_a_missing_library_says_how_to_install_it(gpt_cfg, prep, monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", None)  # import openai now raises ImportError
    with pytest.raises(BrainError, match=r"marginalia\[openai\]"):
        GPTBrain(gpt_cfg).ask(prep, [], "q", [])


def test_a_key_builds_a_real_client_without_calling_the_network(gpt_cfg):
    assert isinstance(GPTBrain(gpt_cfg).client, openai.OpenAI)
