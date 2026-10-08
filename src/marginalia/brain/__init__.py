"""Talks to the model: builds the prompt from the screen, parses the answer and pointer targets.

    prompt   what we send (system prompt, OCR lines, history)
    parsing  what comes back (the JSON envelope, whole or still arriving)
    claude   the Messages API call, streamed
    demo     canned replies for --demo
"""
from .claude import ClaudeBrain
from .demo import DemoBrain
from .parsing import MAX_LABEL, MAX_POINTS, parse_reply, partial_answer
from .prompt import ANSWER_SCHEMA, MAX_HISTORY_CHARS, MAX_OCR_LINES, SYSTEM_PROMPT, build_user_text, select_lines
from .types import Answer, BrainError, Cancelled, Point, Usage

__all__ = [
    "ANSWER_SCHEMA",
    "MAX_HISTORY_CHARS",
    "MAX_LABEL",
    "MAX_OCR_LINES",
    "MAX_POINTS",
    "SYSTEM_PROMPT",
    "Answer",
    "BrainError",
    "Cancelled",
    "ClaudeBrain",
    "DemoBrain",
    "Point",
    "Usage",
    "build_user_text",
    "parse_reply",
    "partial_answer",
    "select_lines",
]
