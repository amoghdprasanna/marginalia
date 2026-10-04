"""Reading the model's reply: the JSON envelope with the answer and its points."""
from __future__ import annotations

import json
import re

from .types import Answer, Point


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


# LaTeX commands that collide with JSON escapes: "\beta" would decode as backspace + "eta".
# \b and \f never belong in an answer, so any letters after them are LaTeX. For \n, \t, \r only
# known commands count, so a real newline before a word ("\nThe") is left alone.
# An already-escaped backslash pair in the JSON is matched first and kept, so correct JSON is untouched.
_LATEX_COLLISIONS = re.compile(
    r"\\\\|\\(?=[bf][a-zA-Z]|(?:nu|neq|nabla|not|ni|theta|tau|times|tilde|text|top|to|rho|rangle|right|rightarrow)\b)"
)


def _loads_lenient(s: str):
    s = _LATEX_COLLISIONS.sub(lambda m: m.group(0) if len(m.group(0)) == 2 else "\\\\", s)
    for candidate in (s, re.sub(r'\\(?![\\"/bfnrtu])', r"\\\\", s)):  # 2nd try fixes other stray backslashes
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue
    return None


def parse_reply(raw: str, model: str = "", elapsed: float = 0.0) -> Answer:
    txt = raw.strip()
    txt = re.sub(r"^```(?:json)?\s*", "", txt)
    txt = re.sub(r"\s*```$", "", txt)
    start, end = txt.find("{"), txt.rfind("}")
    data = _loads_lenient(txt[start : end + 1]) if start != -1 and end > start else None
    if not isinstance(data, dict) or "answer" not in data:
        return Answer(raw.strip() or "(The model returned an empty reply.)", [], model, elapsed, raw)

    points: list[Point] = []
    for p in data.get("points") or []:
        if not isinstance(p, dict):
            continue
        image = "zoom" if str(p.get("image", "full")).lower().startswith("zoom") else "full"
        x, y = _num(p.get("x")), _num(p.get("y"))
        pair = p.get("point") or p.get("xy")
        if (x is None or y is None) and isinstance(pair, (list, tuple)) and len(pair) == 2:
            x, y = _num(pair[0]), _num(pair[1])
        line = p.get("line")
        line = int(line) if isinstance(line, (int, float)) and not isinstance(line, bool) else None
        if (x is None or y is None) and line is None:
            continue
        label = str(p.get("label") or "").strip()[:48] or "here"
        points.append(Point(image, x, y, line, label))
    return Answer(str(data["answer"]).strip(), points, model, elapsed, raw)
