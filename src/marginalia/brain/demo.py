"""Canned replies, so the overlay can be tried without an API key."""
from __future__ import annotations

import time

from ..capture import Prepared
from ..ocr import TextLine
from .types import Answer, Point


class DemoBrain:
    """Canned replies, so you can try the overlay and pointer without an API key."""

    model = "demo"

    def __init__(self, delay: float = 1.0) -> None:
        self.delay = delay  # feels like a real call; tests pass 0

    def ask(self, prep: Prepared, lines: list[TextLine], question: str, history: list[tuple[str, str]]) -> Answer:
        time.sleep(self.delay)
        points = [Point("zoom", *prep.cursor_zoom, None, "what you asked about")]
        text = (
            "**Demo mode.** This canned reply lets you check the overlay without an API key.\n\n"
            f"You asked: *{question}*\n\n"
            "With a key set, Claude reads both screenshots (plus OCR text when available), "
            "answers here, and points at the parts of the screen it is talking about."
        )
        return Answer(text, points, "demo", self.delay, "")
