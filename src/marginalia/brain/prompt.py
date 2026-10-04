"""What we tell the model: the system prompt and the per-question text that goes with the images."""
from __future__ import annotations

from ..capture import Prepared
from ..ocr import TextLine

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
