"""What the brain hands back: an answer, its pointer targets, and errors fit to show the user."""
from __future__ import annotations

from dataclasses import dataclass, field


class BrainError(Exception):
    """An error with a message that is safe and useful to show in the bubble."""


@dataclass
class Point:
    image: str
    x: float | None
    y: float | None
    line: int | None
    label: str


@dataclass
class Answer:
    text: str
    points: list[Point] = field(default_factory=list)
    model: str = ""
    elapsed: float = 0.0
    raw: str = ""
