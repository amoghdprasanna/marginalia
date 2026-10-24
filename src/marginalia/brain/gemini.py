"""Google's Gemini models: one streamed generateContent call per question (ADR 0027)."""
from __future__ import annotations

import importlib
from collections.abc import Callable

from ..capture import Prepared, to_png_bytes
from ..ocr import TextLine
from ..providers import PROVIDERS
from .errors import missing_key, missing_sdk
from .parsing import CUT_OFF, Progress, parse_reply
from .prompt import ANSWER_SCHEMA, PER_MILLE, build_user_text, from_units, system_prompt
from .types import Answer, BrainError, Usage

PROVIDER = PROVIDERS["gemini"]
# Current Gemini models think at low, medium or high; our two deeper levels ask for its deepest.
THINKING = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}
DECLINED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT"}


def read_usage(meta) -> Usage | None:
    if meta is None:
        return None
    cached = getattr(meta, "cached_content_token_count", 0) or 0
    thoughts = getattr(meta, "thoughts_token_count", 0) or 0
    return Usage(
        input_tokens=(getattr(meta, "prompt_token_count", 0) or 0) - cached,
        # Thinking is billed as output, as it is for Claude.
        output_tokens=(getattr(meta, "candidates_token_count", 0) or 0) + thoughts,
        cache_read=cached,
    )


def _name(value) -> str:
    """An SDK enum (FinishReason.MAX_TOKENS) or a plain string, as its bare name."""
    return str(getattr(value, "name", value) or "").rsplit(".", 1)[-1]


def _transport_errors() -> tuple[type[Exception], ...]:
    """Network failures surface as the HTTP library's own errors; the SDK may use httpx or httpx2."""
    found = []
    for module in ("httpx", "httpx2"):
        try:
            found.append(importlib.import_module(module).TransportError)
        except (ImportError, AttributeError):
            pass
    return tuple(found)


def friendly(errors, exc: Exception, model: str) -> BrainError:
    """A google.genai.errors.APIError, worded for the bubble."""
    code, msg = getattr(exc, "code", 0) or 0, str(getattr(exc, "message", "") or exc)
    if code in (401, 403) or "API key not valid" in msg or "API_KEY_INVALID" in str(exc):
        return BrainError("Your API key was rejected. Check it in Settings.", "settings")
    if code == 404:
        return BrainError(f"The model '{model}' isn't available to your key. Pick another in Settings.", "settings")
    if code == 429:
        return BrainError("Too many requests, or your Gemini quota is used up. Wait a little, then try again.", "retry")
    if isinstance(exc, errors.ServerError) or code >= 500:
        return BrainError(f"Gemini is having trouble right now (error {code}). Try again in a moment.", "retry")
    return BrainError(f"Gemini couldn't process this request ({msg[:200]}).")


class GeminiBrain:
    """Calls the Gemini API. `client` is injectable so tests never touch the network."""

    name = PROVIDER.name
    units = PER_MILLE

    def __init__(self, cfg, client=None) -> None:
        self.cfg = cfg
        self.model = cfg.model
        self.client = client
        self.problem: BrainError | None = None
        if self.client is None and cfg.api_key:
            try:
                from google.genai import Client
            except ImportError:
                self.problem = missing_sdk(self.name, PROVIDER.install_hint())
            else:
                self.client = Client(api_key=cfg.api_key)
        self.system = system_prompt(cfg.user_context, self.units)

    @staticmethod
    def _image(img) -> dict:
        return {"inline_data": {"mime_type": "image/png", "data": to_png_bytes(img)}}

    def build_request(self, prep: Prepared, lines: list[TextLine], question: str, history) -> dict:
        text = build_user_text(prep, lines, question, history, self.units)
        return {
            "model": self.model,
            "contents": [{"role": "user", "parts": [self._image(prep.full), self._image(prep.zoom), {"text": text}]}],
            "config": {
                "system_instruction": self.system,
                "max_output_tokens": self.cfg.max_tokens,
                "response_mime_type": "application/json",
                "response_json_schema": ANSWER_SCHEMA,
                "thinking_config": {"thinking_level": THINKING.get(self.cfg.effort, "medium")},
                # More tokens per image: small print on a screenshot is the whole point.
                "media_resolution": "MEDIA_RESOLUTION_HIGH",
            },
        }

    def ask(
        self,
        prep: Prepared,
        lines: list[TextLine],
        question: str,
        history: list[tuple[str, str]],
        on_text: Callable[[str], None] | None = None,
    ) -> Answer:
        """Stream the reply, as ClaudeBrain.ask does; on_text may raise Cancelled to stop it."""
        if self.problem is not None:
            raise self.problem
        if self.client is None:
            raise missing_key(self.name)
        from google.genai import errors

        request = self.build_request(prep, lines, question, history)
        progress = Progress(on_text)
        finish, blocked, meta, model = "", "", None, self.model
        stream = None
        try:
            stream = self.client.models.generate_content_stream(**request)
            for chunk in stream:
                feedback = getattr(chunk, "prompt_feedback", None)
                if feedback is not None and getattr(feedback, "block_reason", None):
                    blocked = _name(feedback.block_reason)
                for cand in getattr(chunk, "candidates", None) or []:
                    for part in getattr(getattr(cand, "content", None), "parts", None) or []:
                        if getattr(part, "text", None) and not getattr(part, "thought", False):
                            progress.add(part.text)
                    if getattr(cand, "finish_reason", None):
                        finish = _name(cand.finish_reason)
                meta = getattr(chunk, "usage_metadata", None) or meta
                model = getattr(chunk, "model_version", None) or model
        except errors.APIError as exc:
            raise friendly(errors, exc, self.model) from exc
        except _transport_errors() as exc:
            raise BrainError("Couldn't reach Gemini. Check your internet connection, then try again.", "retry") from exc
        finally:
            close = getattr(stream, "close", None)
            if close is not None:  # also when Cancelled: closing the generator drops the connection
                close()

        if blocked or finish in DECLINED:
            raise BrainError("Gemini declined to answer this one. Try asking it a different way.")
        answer = parse_reply(progress.raw, model, progress.elapsed())
        # Gemini answered on its 0-1000 grid; everything downstream works in the image's pixels.
        for p in answer.points:
            p.x, p.y = from_units(prep, p.image, p.x, p.y, self.units)
        answer.usage = read_usage(meta)
        answer.first_text = progress.first_text
        if finish == "MAX_TOKENS":
            answer.text += CUT_OFF
        return answer
