"""Optional OCR. It gives the model exact text for small fonts and gives the pointer
real text-line boxes to snap to, which makes pointing noticeably more precise.

On macOS it uses the system's own text recognition (Vision), which adds almost nothing to the
app; elsewhere RapidOCR (pure pip install, no system packages). See ADR 0026. If neither is
installed, everything still works from the screenshots alone.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from PIL import Image


@dataclass
class TextLine:
    id: int
    text: str
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 in physical px
    score: float


def _apple_vision():
    """An engine that takes a PIL image and returns (quad, text, score) in that image's pixels."""
    if sys.platform != "darwin":
        raise ImportError("Apple Vision is macOS only")
    import Foundation
    import objc
    import Quartz
    import Vision

    def engine(img: Image.Image) -> list[tuple]:
        rgba = img.convert("RGBA")
        W, H = rgba.size
        with objc.autorelease_pool():  # we run on worker threads, which have no pool of their own
            cg = Quartz.CGImageCreate(
                W, H, 8, 32, W * 4, Quartz.CGColorSpaceCreateDeviceRGB(), Quartz.kCGImageAlphaNoneSkipLast,
                Quartz.CGDataProviderCreateWithCFData(rgba.tobytes()), None, False, Quartz.kCGRenderingIntentDefault,
            )  # fmt: skip
            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(False)  # it "corrects" code and symbols, and halves their scores
            no_options = Foundation.NSDictionary.dictionary()  # not {}: macOS 27 rejects PyObjC's proxy for it
            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, no_options)
            ok, error = handler.performRequests_error_([request], None)
            if not ok:
                raise RuntimeError(f"Vision text recognition failed: {error}")
            raw = []
            for obs in request.results() or []:
                best = obs.topCandidates_(1)
                if not best:
                    continue
                bb = obs.boundingBox()  # 0..1, origin at the bottom left
                x1, x2 = bb.origin.x * W, (bb.origin.x + bb.size.width) * W
                y1, y2 = (1 - bb.origin.y - bb.size.height) * H, (1 - bb.origin.y) * H
                raw.append(([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], best[0].string(), float(best[0].confidence())))
            return raw

    return engine


def _rapidocr_v1():
    from rapidocr_onnxruntime import RapidOCR  # bundles its models, no download

    return RapidOCR()


def _rapidocr_v2():
    from rapidocr import RapidOCR  # newer package, downloads models on first run

    return RapidOCR()


# Tried in order; the first that loads wins. Each returns an engine; the kind says how to read its output.
LOADERS = (("vision", _apple_vision), ("v1", _rapidocr_v1), ("v2", _rapidocr_v2))


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
        if not self.available:
            return []
        scale = min(1.0, max_edge / max(image.size))
        img = image if scale == 1.0 else image.resize(
            (round(image.width * scale), round(image.height * scale)), Image.LANCZOS
        )

        raw: list[tuple] = []
        if self.kind == "vision":
            raw = self.engine(img)
        elif self.kind == "v1":
            result, _ = self.engine(_bgr(img))
            for box, text, score in result or []:
                raw.append((box, text, float(score)))
        else:
            result = self.engine(_bgr(img))
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


def _bgr(img: Image.Image):
    import numpy as np

    return np.ascontiguousarray(np.asarray(img.convert("RGB"))[:, :, ::-1])  # RapidOCR wants BGR, like OpenCV
