"""The real brain: one Messages API call per question."""
from __future__ import annotations

import time

from ..capture import Prepared, to_b64_png
from ..ocr import TextLine
from .parsing import parse_reply
from .prompt import ANSWER_SCHEMA, SYSTEM_PROMPT, build_user_text
from .types import Answer, BrainError, Usage


def read_usage(resp) -> Usage | None:
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    return Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


class ClaudeBrain:
    """Calls the Messages API. `client` is injectable so tests never touch the network."""

    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, cfg, client=None) -> None:
        self.cfg = cfg
        self.model = cfg.model
        self.client = client
        if self.client is None and cfg.api_key:
            import anthropic

            self.client = anthropic.Anthropic(api_key=cfg.api_key)
        self.system = SYSTEM_PROMPT.replace("{user_context}", cfg.user_context)

    @staticmethod
    def _image(img) -> dict:
        # We resize to the exact size the API would use (capture.resized_size), so the API never
        # rescales and the coordinates it answers in match the pixels we sent.
        return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": to_b64_png(img)}}

    def build_request(self, prep: Prepared, lines: list[TextLine], question: str, history) -> dict:
        text = build_user_text(prep, lines, question, history)
        content = [self._image(prep.full), self._image(prep.zoom), {"type": "text", "text": text}]
        return {
            "model": self.model,
            "max_tokens": self.cfg.max_tokens,
            # The system prompt is identical on every call, so it is cached (ADR 0011). Images and the
            # question come after the breakpoint because they change every time.
            "system": [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
            "output_config": {
                "effort": self.cfg.effort,
                "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
            },
            # On a safety decline the API re-runs the request on Anthropic's recommended model.
            "betas": [self.FALLBACK_BETA],
            "fallbacks": "default",
        }

    def ask(self, prep: Prepared, lines: list[TextLine], question: str, history: list[tuple[str, str]]) -> Answer:
        import anthropic

        if self.client is None:
            raise BrainError(
                "No API key found. Put ANTHROPIC_API_KEY=... in a .env file in the folder you start Marginalia from, "
                "or start with --demo to try the interface without one."
            )
        request = self.build_request(prep, lines, question, history)
        t0 = time.time()
        try:
            resp = self.client.beta.messages.create(**request)
        except anthropic.BadRequestError as exc:
            msg = str(exc)
            if "image" in msg and ("exceed" in msg or "too large" in msg):
                raise BrainError(
                    "The model rejected the screenshot size. If MARGINALIA_HIRES=1 is set, this "
                    "model is on the standard image tier; set it to 0."
                ) from exc
            raise BrainError(f"The API rejected the request: {msg[:300]}") from exc
        except anthropic.AuthenticationError as exc:
            raise BrainError("The API key was rejected. Check ANTHROPIC_API_KEY in your .env file.") from exc
        except anthropic.NotFoundError as exc:
            raise BrainError(f"Model '{self.model}' was not found. Set MARGINALIA_MODEL in .env.") from exc
        except anthropic.RateLimitError as exc:
            raise BrainError("Rate limited by the API. Wait a few seconds and ask again.") from exc
        except anthropic.APIStatusError as exc:
            raise BrainError(f"API error {exc.status_code}: {str(exc)[:300]}") from exc
        except anthropic.APIConnectionError as exc:
            raise BrainError("Could not reach the API. Check your internet connection.") from exc

        if resp.stop_reason == "refusal":
            raise BrainError("Claude declined to answer this one. Try rephrasing the question.")
        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        answer = parse_reply(raw, getattr(resp, "model", self.model), time.time() - t0)
        answer.usage = read_usage(resp)
        if resp.stop_reason == "max_tokens":
            answer.text += "\n\n*(Cut off at the length limit. Raise MARGINALIA_MAX_TOKENS for longer answers.)*"
        return answer
