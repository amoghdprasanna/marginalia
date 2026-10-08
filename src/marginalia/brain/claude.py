"""The real brain: one streamed Messages API call per question."""
from __future__ import annotations

import time
from collections.abc import Callable

from ..capture import Prepared, to_b64_png
from ..ocr import TextLine
from .parsing import parse_reply, partial_answer
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

    def ask(
        self,
        prep: Prepared,
        lines: list[TextLine],
        question: str,
        history: list[tuple[str, str]],
        on_text: Callable[[str], None] | None = None,
    ) -> Answer:
        """Stream the reply. `on_text` gets the whole answer-so-far each time it grows (ADR 0012).

        `on_text` runs on this (worker) thread. It may raise Cancelled to stop the stream early,
        which closes the connection so an abandoned answer stops costing tokens.
        """
        import anthropic

        if self.client is None:
            raise BrainError(
                "Marginalia needs an Anthropic API key to answer. Add one in Settings; it is kept in your keychain.",
                "settings",
            )
        request = self.build_request(prep, lines, question, history)
        t0 = time.monotonic()
        first_text: float | None = None
        raw, shown = "", ""
        try:
            with self.client.beta.messages.stream(**request) as stream:
                for chunk in stream.text_stream:
                    raw += chunk
                    text = partial_answer(raw)
                    if text and text != shown:
                        shown = text
                        if first_text is None:
                            first_text = time.monotonic() - t0
                        if on_text is not None:
                            on_text(text)
                resp = stream.get_final_message()
        except anthropic.BadRequestError as exc:
            msg = str(exc)
            if "image" in msg and ("exceed" in msg or "too large" in msg):
                raise BrainError(
                    "This model can't take screenshots that large. Turn off High-resolution images in Settings.",
                    "settings",
                ) from exc
            raise BrainError(f"Claude couldn't process this request ({msg[:200]}).") from exc
        except anthropic.AuthenticationError as exc:
            raise BrainError("Your API key was rejected. Check it in Settings.", "settings") from exc
        except anthropic.NotFoundError as exc:
            message = f"The model '{self.model}' isn't available to your key. Pick another in Settings."
            raise BrainError(message, "settings") from exc
        except anthropic.RateLimitError as exc:
            raise BrainError("Too many requests right now. Wait a few seconds, then try again.", "retry") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                message = f"Claude is having trouble right now (error {exc.status_code}). Try again in a moment."
                raise BrainError(message, "retry") from exc
            raise BrainError(f"Claude returned an error ({exc.status_code}): {str(exc)[:200]}") from exc
        except anthropic.APIConnectionError as exc:
            message = "Couldn't reach Claude. Check your internet connection, then try again."
            raise BrainError(message, "retry") from exc
        except anthropic.APIError as exc:  # an error event in the middle of the stream
            raise BrainError("The answer was interrupted. Try again.", "retry") from exc

        if resp.stop_reason == "refusal":
            raise BrainError("Claude declined to answer this one. Try asking it a different way.")
        # With a mid-answer fallback the reply spans several text blocks; together they are one reply.
        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        answer = parse_reply(raw, getattr(resp, "model", self.model), time.monotonic() - t0)
        answer.usage = read_usage(resp)
        answer.first_text = first_text
        if resp.stop_reason == "max_tokens":
            answer.text += "\n\n*(Cut off at the length limit. Raise Max tokens in Settings for longer answers.)*"
        return answer
