"""Canned replies, so the overlay can be tried without an API key."""
from __future__ import annotations

import re
import time
from collections.abc import Callable

from ..capture import Prepared
from ..ocr import TextLine
from .types import Answer, Point


class DemoBrain:
    """Canned replies, so you can try the overlay, streaming and pointer without an API key."""

    model = "demo"

    def __init__(self, delay: float = 1.0) -> None:
        self.delay = delay  # feels like a real call; tests pass 0

    def ask(
        self,
        prep: Prepared,
        lines: list[TextLine],
        question: str,
        history: list[tuple[str, str]],
        on_text: Callable[[str], None] | None = None,
    ) -> Answer:
        points = [Point("zoom", *prep.cursor_zoom, None, "what you asked about")]
        text = (
            "**Demo mode.** This canned reply lets you check the overlay without an API key.\n\n"
            f"You asked: *{question}*\n\n"
            "With a key set, Claude reads both screenshots (plus OCR text when available), "
            "writes the answer here as it thinks of it, and points at the parts of the screen it is talking about."
        )
        time.sleep(self.delay * 0.6)  # "reading the screen"
        words = re.findall(r"\S+\s*", text)
        for i in range(1, len(words) + 1):  # then the words arrive, like a real stream
            time.sleep(self.delay * 0.4 / len(words))
            if on_text is not None:
                on_text("".join(words[:i]))
        return Answer(text, points, "demo", self.delay, "", first_text=self.delay * 0.6)
