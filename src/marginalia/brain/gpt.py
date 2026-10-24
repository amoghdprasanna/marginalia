"""OpenAI's models: one streamed Responses API call per question (ADR 0027)."""
from __future__ import annotations

from collections.abc import Callable

from ..capture import Prepared, to_b64_png
from ..ocr import TextLine
from ..providers import PROVIDERS
from .errors import friendly, missing_key, missing_sdk
from .parsing import CUT_OFF, Progress, parse_reply
from .prompt import ANSWER_SCHEMA, build_user_text, system_prompt
from .types import Answer, BrainError, Usage

PROVIDER = PROVIDERS["openai"]


def read_usage(resp) -> Usage | None:
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
    return Usage(
        # OpenAI counts cached tokens inside input_tokens; Usage keeps them apart, as Anthropic does.
        input_tokens=(getattr(u, "input_tokens", 0) or 0) - cached,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read=cached,
    )


def refused(resp) -> bool:
    """A refusal arrives as a `refusal` content part instead of output_text, with status completed."""
    for item in getattr(resp, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", "") == "refusal":
                return True
    return False


class GPTBrain:
    """Calls the Responses API. `client` is injectable so tests never touch the network."""

    name = PROVIDER.name

    def __init__(self, cfg, client=None) -> None:
        self.cfg = cfg
        self.model = cfg.model
        self.client = client
        self.problem: BrainError | None = None
        if self.client is None and cfg.api_key:
            try:
                import openai
            except ImportError:
                self.problem = missing_sdk(self.name, PROVIDER.install_hint())
            else:
                self.client = openai.OpenAI(api_key=cfg.api_key)
        self.system = system_prompt(cfg.user_context)

    @staticmethod
    def _image(img) -> dict:
        # "original" keeps our size (current models only shrink past 65,535 px), so the pixels the
        # model answers in are the ones we sent, as with Claude (ADR 0003).
        return {"type": "input_image", "image_url": f"data:image/png;base64,{to_b64_png(img)}", "detail": "original"}

    def build_request(self, prep: Prepared, lines: list[TextLine], question: str, history) -> dict:
        text = build_user_text(prep, lines, question, history)
        content = [self._image(prep.full), self._image(prep.zoom), {"type": "input_text", "text": text}]
        return {
            "model": self.model,
            # The fixed prompt goes first and the images after it, so OpenAI's automatic prefix caching
            # can reuse it once it is long enough (it needs 1024 tokens; ours is shorter today).
            "instructions": self.system,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": self.cfg.max_tokens,
            # Our five levels are OpenAI's too (low..max) on current models.
            "reasoning": {"effort": self.cfg.effort},
            "text": {"format": {"type": "json_schema", "name": "answer", "schema": ANSWER_SCHEMA, "strict": True}},
            "store": False,  # screenshots may be private; nothing needs the response kept server-side
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
        import openai

        request = self.build_request(prep, lines, question, history)
        progress = Progress(on_text)
        resp = None
        try:
            with self.client.responses.create(**request, stream=True) as stream:
                for event in stream:
                    kind = getattr(event, "type", "")
                    if kind == "response.output_text.delta":
                        progress.add(event.delta)
                    elif kind in ("response.completed", "response.incomplete", "response.failed"):
                        resp = event.response
                    elif kind == "error":
                        raise BrainError(f"{self.name} stopped with an error: {getattr(event, 'message', '')[:200]}")
        except openai.APIError as exc:
            raise friendly(openai, exc, self.name, self.model) from exc

        if resp is None:
            raise BrainError("The answer was interrupted. Try again.", "retry")
        if getattr(resp, "status", "") == "failed":
            error = getattr(resp, "error", None)
            raise BrainError(f"{self.name} couldn't answer ({getattr(error, 'message', 'no reason given')[:200]}).")
        reason = getattr(getattr(resp, "incomplete_details", None), "reason", None)
        if refused(resp) or reason == "content_filter":
            raise BrainError(f"{self.name} declined to answer this one. Try asking it a different way.")
        answer = parse_reply(progress.raw, getattr(resp, "model", self.model) or self.model, progress.elapsed())
        answer.usage = read_usage(resp)
        answer.first_text = progress.first_text
        if reason == "max_output_tokens":
            answer.text += CUT_OFF
        return answer
