"""Talks to the model: builds the prompt from the screen, parses the answer and pointer targets.

    prompt   what we send (system prompt, OCR lines, history)
    parsing  what comes back (the JSON envelope, whole or still arriving)
    errors   SDK errors worded for the bubble
    claude   Anthropic's Messages API, streamed
    gpt      OpenAI's Responses API, streamed
    gemini   Google's Gemini API, streamed
    demo     canned replies for --demo

Every brain has the same `ask`, so the controller never knows which one it holds (ADR 0027).
"""
from .claude import ClaudeBrain
from .demo import DemoBrain
from .gemini import GeminiBrain
from .gpt import GPTBrain
from .parsing import MAX_LABEL, MAX_POINTS, Progress, parse_reply, partial_answer
from .prompt import ANSWER_SCHEMA, MAX_HISTORY_CHARS, MAX_OCR_LINES, SYSTEM_PROMPT, build_user_text, select_lines
from .types import Answer, BrainError, Cancelled, Point, Usage

BRAINS = {"anthropic": ClaudeBrain, "openai": GPTBrain, "gemini": GeminiBrain}


def brain_for(cfg):
    """The brain for cfg.provider. The SDK is imported only when that provider is used."""
    return BRAINS[cfg.provider](cfg)


__all__ = [
    "BRAINS",
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
    "GPTBrain",
    "GeminiBrain",
    "Point",
    "Progress",
    "Usage",
    "brain_for",
    "build_user_text",
    "parse_reply",
    "partial_answer",
    "select_lines",
]
