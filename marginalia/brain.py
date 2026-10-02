"""Talks to the model: builds the prompt from the screen, parses the answer and pointer targets."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from .capture import Prepared, to_b64_png
from .ocr import TextLine

SYSTEM_PROMPT = """You are Marginalia, a study companion that floats over the user's screen while they read papers, watch lectures, and work through problems.

{user_context}

Each turn you receive two screenshots of the screen the user is looking at, sometimes OCR text, and their question.

How to answer:
1. Words like "this", "here", "that equation", or "what he just said" refer to what is at or near the red cursor ring, or to the speaker in a visible video.
2. Answer the actual question in the first sentence. Then add only what helps understanding. Usually 60 to 200 words; go longer only for a derivation or when asked.
3. Keep apart what is on the screen and what you know from background knowledge. If something is too small or blurry to read, say so rather than guess. Never invent text that is not on the screen.
4. Write math with Unicode inline (|ψ⟩, ⟨0|, ⊗, †, √2, Σ, ρ, Tr, ≈), not LaTeX; the answer box cannot render LaTeX. Markdown (bold, lists, `code`) is fine.
5. Point at things on the screen when it helps: the term you define, the equation you explain, the figure panel, the variable that answers the question. Usually one point is enough; add more (at most 4) only for separate targets far apart on screen, never two points on the same thing. Each gets a label of 2 to 5 words. Give integer pixel coordinates of the target's center in the image where you located it: "zoom" for things inside the close-up (more precise), otherwise "full". If the target is one of the OCR lines, also give its "line" id. Do not point at the red ring itself unless asked. Use no points if nothing on screen is worth pointing at.

Reply with a single JSON object and nothing else (no code fences):
{"answer": "<markdown>", "points": [{"image": "full", "x": 0, "y": 0, "line": null, "label": "short label"}]}"""

MAX_OCR_LINES = 220
MAX_HISTORY_CHARS = 1200


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


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _loads_lenient(s: str):
    for candidate in (s, re.sub(r'\\(?![\\"/bfnrtu])', r"\\\\", s)):  # 2nd try fixes stray LaTeX backslashes
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


def select_lines(lines: list[TextLine], prep: Prepared, limit: int = MAX_OCR_LINES) -> list[TextLine]:
    if len(lines) <= limit:
        return lines
    cx, cy = prep.to_physical("full", *prep.cursor_full)

    def dist(l: TextLine) -> float:
        x1, y1, x2, y2 = l.box
        dx = max(x1 - cx, 0, cx - x2)
        dy = max(y1 - cy, 0, cy - y2)
        return dx * dx + 4 * dy * dy

    keep = sorted(lines, key=dist)[:limit]
    return sorted(keep, key=lambda l: l.id)


def build_user_text(prep: Prepared, lines: list[TextLine], question: str, history: list[tuple[str, str]]) -> str:
    fw, fh = prep.full.size
    zw, zh = prep.zoom.size
    parts = [
        f'Image 1 ("full"): the whole screen, {fw}x{fh} px. The red ring marks the mouse cursor at {list(prep.cursor_full)}.',
        f'Image 2 ("zoom"): close-up around the cursor, {zw}x{zh} px. The red ring is at {list(prep.cursor_zoom)}.',
    ]
    if lines:
        parts.append(
            "OCR text lines on screen as [id] [x1, y1, x2, y2] text, with boxes in full-image px. "
            "OCR often garbles math, so trust the images for equations and symbols:"
        )
        for l in select_lines(lines, prep):
            x1, y1 = prep.physical_to_full(l.box[0], l.box[1])
            x2, y2 = prep.physical_to_full(l.box[2], l.box[3])
            parts.append(f"[{l.id}] [{x1}, {y1}, {x2}, {y2}] {l.text}")
    else:
        parts.append("OCR: not available for this screen.")
    if history:
        parts.append("Earlier in this session (oldest first; the screen may have changed since):")
        for q, a in history:
            parts.append(f"Q: {q}\nA: {a[:MAX_HISTORY_CHARS]}")
    parts.append(f"Question: {question}")
    return "\n".join(parts)


class ClaudeBrain:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.model = cfg.model
        self.client = None
        if cfg.api_key:
            import anthropic

            self.client = anthropic.Anthropic(api_key=cfg.api_key)
        self.system = SYSTEM_PROMPT.replace("{user_context}", cfg.user_context)
        self._strict_images = True

    def _image(self, img) -> dict:
        block = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": to_b64_png(img)}}
        if self._strict_images:
            # Fail loudly instead of letting the API resize the image and shift every coordinate.
            block["transformations"] = {"oversized_image": "error"}
        return block

    def ask(self, prep: Prepared, lines: list[TextLine], question: str, history: list[tuple[str, str]]) -> Answer:
        import anthropic

        if self.client is None:
            raise BrainError(
                "No API key found. Put ANTHROPIC_API_KEY=... in a .env file next to run.py, "
                "or start with --demo to try the interface without one."
            )
        text = build_user_text(prep, lines, question, history)
        t0 = time.time()
        for attempt in range(2):
            content = [self._image(prep.full), self._image(prep.zoom), {"type": "text", "text": text}]
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.cfg.max_tokens,
                    system=self.system,
                    messages=[{"role": "user", "content": content}],
                )
                break
            except anthropic.BadRequestError as exc:
                msg = str(exc)
                if attempt == 0 and "transformations" in msg and "exceed" not in msg:
                    self._strict_images = False  # API without this field: retry without it
                    continue
                if "exceed" in msg and "image" in msg:
                    raise BrainError(
                        "The model rejected the screenshot size. If MARGINALIA_HIRES=1 is set, this "
                        "model is on the standard image tier; set it to 0."
                    ) from exc
                raise BrainError(f"The API rejected the request: {msg[:300]}") from exc
            except anthropic.AuthenticationError as exc:
                raise BrainError("The API key was rejected. Check ANTHROPIC_API_KEY in your .env file.") from exc
            except anthropic.NotFoundError as exc:
                raise BrainError(f"Model '{self.model}' was not found. Set MARGINALIA_MODEL in .env.") from exc
            except anthropic.RateLimitError as exc:
                raise BrainError("Rate limited by the API. Wait a few seconds and ask again.") from exc
            except anthropic.APIConnectionError as exc:
                raise BrainError("Could not reach the API. Check your internet connection.") from exc
            except anthropic.APIStatusError as exc:
                raise BrainError(f"API error {exc.status_code}: {str(exc)[:300]}") from exc

        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        return parse_reply(raw, self.model, time.time() - t0)


class DemoBrain:
    """Canned replies, so you can try the overlay and pointer without an API key."""

    model = "demo"

    def ask(self, prep: Prepared, lines: list[TextLine], question: str, history: list[tuple[str, str]]) -> Answer:
        time.sleep(1.0)
        points = [Point("zoom", *prep.cursor_zoom, None, "what you asked about")]
        text = (
            "**Demo mode.** This canned reply lets you check the overlay without an API key.\n\n"
            f"You asked: *{question}*\n\n"
            "With a key set, Claude reads both screenshots (plus OCR text when available), "
            "answers here, and points at the parts of the screen it is talking about."
        )
        return Answer(text, points, "demo", 1.0, "")
