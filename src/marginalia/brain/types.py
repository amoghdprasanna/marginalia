"""What the brain hands back: an answer, its pointer targets, and errors fit to show the user."""
from __future__ import annotations

from dataclasses import dataclass, field


class BrainError(Exception):
    """An error with a message that is safe and useful to show in the bubble."""


class Cancelled(Exception):  # noqa: N818 - it is a signal, not an error
    """Raised from an on_text callback to stop streaming an answer nobody is waiting for."""


@dataclass
class Point:
    image: str
    x: float | None
    y: float | None
    line: int | None
    label: str


@dataclass
class Usage:
    """Token counts for one call, as the API reports them. The eval turns these into cost."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0


@dataclass
class Answer:
    text: str
    points: list[Point] = field(default_factory=list)
    model: str = ""
    elapsed: float = 0.0
    raw: str = ""
    usage: Usage | None = None
    first_text: float | None = None  # seconds until the first words of the answer
