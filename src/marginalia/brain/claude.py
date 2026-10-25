"""The real brain: one streamed Messages API call per question."""
from __future__ import annotations

from collections.abc import Callable

from ..capture import Prepared, to_b64_png
from ..ocr import TextLine
from .errors import friendly, missing_key
from .parsing import CUT_OFF, Progress, parse_reply
from .prompt import ANSWER_SCHEMA, build_user_text, system_prompt
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
    name = "Claude"

    def __init__(self, cfg, client=None) -> None:
        self.cfg = cfg
        self.model = cfg.model
        self.client = client
        if self.client is None and cfg.api_key:
            import anthropic

            self.client = anthropic.Anthropic(api_key=cfg.api_key)
        self.system = system_prompt(cfg.user_context)

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
            raise missing_key(self.name)
        request = self.build_request(prep, lines, question, history)
        progress = Progress(on_text)
        try:
            with self.client.beta.messages.stream(**request) as stream:
                for chunk in stream.text_stream:
                    progress.add(chunk)
                resp = stream.get_final_message()
        except anthropic.APIError as exc:
            raise friendly(anthropic, exc, self.name, self.model) from exc

        if resp.stop_reason == "refusal":
            raise BrainError("Claude declined to answer this one. Try asking it a different way.")
        # With a mid-answer fallback the reply spans several text blocks; together they are one reply.
        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        answer = parse_reply(raw, getattr(resp, "model", self.model), progress.elapsed())
        answer.usage = read_usage(resp)
        answer.first_text = progress.first_text
        if resp.stop_reason == "max_tokens":
            answer.text += CUT_OFF
        return answer
