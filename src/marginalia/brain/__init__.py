"""Talks to the model: builds the prompt from the screen, parses the answer and pointer targets.

    prompt   what we send (system prompt, OCR lines, history)
    parsing  what comes back (the JSON envelope)
    claude   the Messages API call
    demo     canned replies for --demo
"""
from .claude import ClaudeBrain
from .demo import DemoBrain
from .parsing import parse_reply
from .prompt import MAX_HISTORY_CHARS, MAX_OCR_LINES, SYSTEM_PROMPT, build_user_text, select_lines
from .types import Answer, BrainError, Point

__all__ = [
    "MAX_HISTORY_CHARS",
    "MAX_OCR_LINES",
    "SYSTEM_PROMPT",
    "Answer",
    "BrainError",
    "ClaudeBrain",
    "DemoBrain",
    "Point",
    "build_user_text",
    "parse_reply",
    "select_lines",
]
