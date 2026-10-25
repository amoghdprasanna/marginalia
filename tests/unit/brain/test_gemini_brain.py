"""GeminiBrain against a fake client: request shape, the 0-1000 grid, streaming, refusals, errors."""

import sys
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors
from helpers import envelope, point_dict

from marginalia.brain import ANSWER_SCHEMA, BrainError, Cancelled, GeminiBrain


def _chunk(text=None, finish=None, thought=False, usage=None, block=None):
    parts = [SimpleNamespace(text=text, thought=thought)] if text is not None else []
    cand = SimpleNamespace(content=SimpleNamespace(parts=parts), finish_reason=finish)
    return SimpleNamespace(
        candidates=[cand],
        usage_metadata=usage,
        model_version="gemini-4-argon-001",
        prompt_feedback=SimpleNamespace(block_reason=block) if block else None,
    )


class FakeStream:
    """What generate_content_stream returns: a generator of chunks, which we must close."""

    def __init__(self, chunks, error=None) -> None:
        self.chunks, self.error = chunks, error
        self.closed = False
        self.read = 0

    def __iter__(self):
        if self.error is not None:
            raise self.error
        for c in self.chunks:
            self.read += 1
            yield c

    def close(self) -> None:
        self.closed = True


class FakeModels:
    def __init__(self, chunks, error) -> None:
        self.chunks, self.error = chunks, error
        self.requests: list[dict] = []
        self.streams: list[FakeStream] = []

    def generate_content_stream(self, **kwargs):
        self.requests.append(kwargs)
        self.streams.append(FakeStream(self.chunks, self.error))
        return self.streams[-1]


def fake_client(text=None, finish="STOP", error=None, extra=(), usage=None):
    text = envelope("hi") if text is None else text
    pieces = [text[i : i + 7] for i in range(0, len(text), 7)]
    chunks = [*extra, *(_chunk(p) for p in pieces[:-1]), _chunk(pieces[-1] if pieces else "", finish, usage=usage)]
    models = FakeModels(chunks, error)
    return SimpleNamespace(models=models), models


@pytest.fixture
def gem_cfg(cfg):
    return replace(cfg, provider="gemini", model="gemini-4-argon")


def test_request_shape(gem_cfg, prep):
    client, models = fake_client()
    GeminiBrain(gem_cfg, client=client).ask(prep, [], "what is d?", [])
    req = models.requests[0]
    assert req["model"] == "gemini-4-argon"
    config = req["config"]
    assert config["response_mime_type"] == "application/json" and config["response_json_schema"] == ANSWER_SCHEMA
    assert config["thinking_config"] == {"thinking_level": "medium"} and config["max_output_tokens"] == 16000
    assert config["media_resolution"] == "MEDIA_RESOLUTION_HIGH"
    assert "0 to 1000" in config["system_instruction"] and "pixel coordinates" not in config["system_instruction"]
    parts = req["contents"][0]["parts"]
    assert [next(iter(p)) for p in parts] == ["inline_data", "inline_data", "text"]
    assert parts[0]["inline_data"]["data"].startswith(b"\x89PNG"), "raw bytes; the SDK encodes them"
    assert "0 to 1000" in parts[2]["text"]


@pytest.mark.parametrize(("effort", "level"), [("low", "low"), ("high", "high"), ("xhigh", "high"), ("max", "high")])
def test_our_five_efforts_map_onto_geminis_three(gem_cfg, prep, effort, level):
    client, models = fake_client()
    GeminiBrain(replace(gem_cfg, effort=effort), client=client).ask(prep, [], "q", [])
    assert models.requests[0]["config"]["thinking_config"] == {"thinking_level": level}


def test_points_come_back_in_image_pixels(gem_cfg, prep):
    reply = envelope("here", [point_dict(image="full", x=500, y=250), point_dict(image="zoom", x=1000, y=0)])
    client, _ = fake_client(text=reply)
    full, zoom = GeminiBrain(gem_cfg, client=client).ask(prep, [], "q", []).points
    assert (full.x, full.y) == (prep.full.width / 2, prep.full.height / 4)
    assert (zoom.x, zoom.y) == (prep.zoom.width, 0)


def test_answer_streams_and_skips_thoughts(gem_cfg, prep):
    client, _ = fake_client(text=envelope("The code distance."), extra=[_chunk("planning…", thought=True)])
    seen = []
    a = GeminiBrain(gem_cfg, client=client).ask(prep, [], "q", [], on_text=seen.append)
    assert seen[-1] == a.text == "The code distance." and len(seen) > 1
    assert a.model == "gemini-4-argon-001"


def test_cancelling_closes_the_stream_early(gem_cfg, prep):
    client, models = fake_client(text=envelope("word " * 50))

    def stop(_text):
        raise Cancelled

    with pytest.raises(Cancelled):
        GeminiBrain(gem_cfg, client=client).ask(prep, [], "q", [], on_text=stop)
    stream = models.streams[0]
    assert stream.closed and stream.read < len(stream.chunks)


def test_cut_off_answer_keeps_the_prose_and_says_so(gem_cfg, prep):
    client, _ = fake_client(text='{"answer": "Because the syndrome', finish="MAX_TOKENS")
    a = GeminiBrain(gem_cfg, client=client).ask(prep, [], "q", [])
    assert a.text.startswith("Because the syndrome") and "length limit" in a.text


@pytest.mark.parametrize("kw", [{"finish": "SAFETY"}, {"extra": [_chunk(block="PROHIBITED_CONTENT")]}])
def test_a_refusal_is_a_friendly_error(gem_cfg, prep, kw):
    client, _ = fake_client(**kw)
    with pytest.raises(BrainError, match="Gemini declined"):
        GeminiBrain(gem_cfg, client=client).ask(prep, [], "q", [])


def _api(cls, code, message, status="X"):
    return cls(code, {"error": {"code": code, "message": message, "status": status}})


@pytest.mark.parametrize(
    ("error", "expected", "action"),
    [
        (_api(errors.ClientError, 400, "API key not valid. Please pass a valid key."), "key was rejected", "settings"),
        (_api(errors.ClientError, 403, "Permission denied"), "key was rejected", "settings"),
        (_api(errors.ClientError, 404, "models/x is not found"), "isn't available", "settings"),
        (_api(errors.ClientError, 429, "Resource exhausted"), "quota", "retry"),
        (_api(errors.ClientError, 400, "Invalid JSON payload"), "Gemini couldn't process", None),
        (_api(errors.ServerError, 503, "overloaded"), "Gemini is having trouble", "retry"),
        (httpx.ConnectError("no route"), "Couldn't reach Gemini", "retry"),
    ],
)
def test_api_errors_say_what_to_do_next(gem_cfg, prep, error, expected, action):
    client, models = fake_client(error=error)
    with pytest.raises(BrainError, match=expected) as err:
        GeminiBrain(gem_cfg, client=client).ask(prep, [], "q", [])
    assert err.value.action == action
    assert models.streams[0].closed


def test_usage_counts_thinking_as_output(gem_cfg, prep):
    meta = SimpleNamespace(
        prompt_token_count=3100, cached_content_token_count=700, candidates_token_count=240, thoughts_token_count=900
    )
    client, _ = fake_client(usage=meta)
    u = GeminiBrain(gem_cfg, client=client).ask(prep, [], "q", []).usage
    assert (u.input_tokens, u.output_tokens, u.cache_read) == (2400, 1140, 700)


def test_missing_key_points_to_settings(gem_cfg, prep):
    with pytest.raises(BrainError, match="Gemini API key") as err:
        GeminiBrain(replace(gem_cfg, api_key=None)).ask(prep, [], "q", [])
    assert err.value.action == "settings"


def test_a_missing_library_says_how_to_install_it(gem_cfg, prep, monkeypatch):
    monkeypatch.setitem(sys.modules, "google.genai", None)
    with pytest.raises(BrainError, match=r"marginalia\[gemini\]"):
        GeminiBrain(gem_cfg).ask(prep, [], "q", [])


def test_a_key_builds_a_real_client_without_calling_the_network(gem_cfg):
    from google import genai

    assert isinstance(GeminiBrain(gem_cfg).client, genai.Client)
