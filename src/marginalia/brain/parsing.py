"""Reading the model's reply: the JSON envelope with the answer and its points.

The API enforces the envelope's schema (ADR 0011), so a reply either parses or was cut off
(length limit, or a refusal mid-answer). For a cut-off reply we still show the prose that arrived.
"""
from __future__ import annotations

import json
import re

from .types import Answer, Point

MAX_POINTS = 4
MAX_LABEL = 48

_ANSWER_START = re.compile(r'"answer"\s*:\s*"')
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def partial_answer(raw: str) -> str | None:
    """The decoded "answer" string from a reply that may stop anywhere, even mid-escape.

    None until the "answer" key has arrived. Escapes are decoded only once complete, so the
    text never shows half of a \\u sequence or a lone backslash.
    """
    m = _ANSWER_START.search(raw)
    if m is None:
        return None
    out: list[str] = []
    i, n = m.end(), len(raw)
    while i < n:
        c = raw[i]
        if c == '"':
            break
        if c != "\\":
            out.append(c)
            i += 1
            continue
        if i + 1 >= n:
            break
        e = raw[i + 1]
        if e != "u":
            out.append(_ESCAPES.get(e, e))
            i += 2
            continue
        try:
            cp = int(raw[i + 2 : i + 6], 16) if len(raw) >= i + 6 else None
            if cp is not None and 0xD800 <= cp < 0xDC00:  # high surrogate: wait for the low half
                low = int(raw[i + 8 : i + 12], 16) if raw[i + 6 : i + 8] == "\\u" and len(raw) >= i + 12 else None
                cp = None if low is None else 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00)
                step = 12
            else:
                step = 6
        except ValueError:
            break
        if cp is None:
            break
        out.append(chr(cp))
        i += step
    return "".join(out)


def _point(p: dict) -> Point:
    image = "zoom" if p.get("image") == "zoom" else "full"
    line = p.get("line")
    label = str(p.get("label") or "").strip()[:MAX_LABEL] or "here"
    return Point(image, float(p["x"]), float(p["y"]), line if isinstance(line, int) else None, label)


def parse_reply(raw: str, model: str = "", elapsed: float = 0.0) -> Answer:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("answer"), str):
        text = (partial_answer(raw) or raw).strip() or "(The model returned an empty reply.)"
        return Answer(text, [], model, elapsed, raw)
    points = []
    for p in (data.get("points") or [])[:MAX_POINTS]:
        try:
            points.append(_point(p))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue  # the schema rules this out; skip rather than lose the whole answer
    return Answer(data["answer"].strip(), points, model, elapsed, raw)
