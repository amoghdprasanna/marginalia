"""Optional OCR. It gives the model exact text for small fonts and gives the pointer
real text-line boxes to snap to, which makes pointing noticeably more precise.

Uses RapidOCR (pure pip install, no system packages). If it is missing, everything
still works from the screenshots alone.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass
class TextLine:
    id: int
    text: str
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 in physical px
    score: float


def _rapidocr_v1():
    from rapidocr_onnxruntime import RapidOCR  # bundles its models, no download

    return RapidOCR()


def _rapidocr_v2():
    from rapidocr import RapidOCR  # newer package, downloads models on first run

    return RapidOCR()


# Tried in order; the first that loads wins. Each returns an engine; the kind says how to read its output.
LOADERS = (("v1", _rapidocr_v1), ("v2", _rapidocr_v2))


class OCR:
    def __init__(self, loaders=LOADERS) -> None:
        self.engine = None
        self.kind = None
        self.error: Exception | None = None
        for kind, load in loaders:
            try:
                self.engine, self.kind = load(), kind
                return
            except Exception as exc:  # noqa: BLE001  (ImportError, or a broken onnxruntime)
                self.error = exc

    @property
    def available(self) -> bool:
        return self.engine is not None

    def read(self, image: Image.Image, max_edge: int = 2200, min_score: float = 0.5) -> list[TextLine]:
        import numpy as np

        if not self.available:
            return []
        scale = min(1.0, max_edge / max(image.size))
        img = image if scale == 1.0 else image.resize(
            (round(image.width * scale), round(image.height * scale)), Image.LANCZOS
        )
        arr = np.ascontiguousarray(np.asarray(img.convert("RGB"))[:, :, ::-1])  # BGR, like OpenCV

        raw: list[tuple] = []
        if self.kind == "v1":
            result, _ = self.engine(arr)
            for box, text, score in result or []:
                raw.append((box, text, float(score)))
        else:
            result = self.engine(arr)
            if getattr(result, "boxes", None) is not None:
                for box, text, score in zip(result.boxes, result.txts, result.scores, strict=False):
                    raw.append((box, text, float(score)))

        lines: list[TextLine] = []
        for box, text, score in raw:
            text = (text or "").strip()
            if not text or score < min_score:
                continue
            xs = [p[0] / scale for p in box]
            ys = [p[1] / scale for p in box]
            lines.append(TextLine(0, text, (min(xs), min(ys), max(xs), max(ys)), score))

        lines.sort(key=lambda l: (round(l.box[1] / 12), l.box[0]))
        for i, line in enumerate(lines):
            line.id = i
        return lines
