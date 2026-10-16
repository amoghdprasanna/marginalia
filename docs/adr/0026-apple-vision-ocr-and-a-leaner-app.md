# 0026. OCR with Apple Vision on macOS, and a leaner app

**Status:** Accepted, 2026-10-16. Supersedes the size and duplicate-FFmpeg consequences of
[0023](0023-pyinstaller-app.md) for macOS; its other decisions stand.

## Context
The packaged macOS app was 432 MB (a 188 MB `.dmg`). Measured by package, about 210 MB of it
was OCR: OpenCV (121 MB, most of it FFmpeg, Tesseract, SDL2 and X11 libraries that RapidOCR
never calls), onnxruntime (72 MB), RapidOCR's models (16 MB), shapely and pyclipper. All of
that does one job, finding text lines on a screenshot, and macOS already ships a text
recogniser: the Vision framework. A further 25 MB was Qt that plugins drag in (QtQuick and
QtQml through the virtual-keyboard input plugin, QtPdf through the PDF image plugin, and Qt's
translations), and 8 MB was `hf_xet`, an optional fast-download backend for huggingface_hub.

On the eval screenshot (2880×1800) and on 10–13 px synthetic text, Vision found the same lines
as RapidOCR, with comparable small errors (`le-3` for `1e-3` where RapidOCR wrote `α` for `≈`),
in 0.2–0.9 s against 1.5–3 s.

## Decision
- **macOS OCR uses Vision** (`VNRecognizeTextRequest`, accurate, through
  `pyobjc-framework-Vision`), tried first in `ocr.LOADERS`; RapidOCR stays the engine elsewhere.
  The `[ocr]` extra installs the right one per platform.
- **Language correction is off.** It rewrites code and symbols and halves their confidence to
  0.5, which sits on our `min_score` cut-off.
- **The macOS bundle excludes the RapidOCR stack** (`rapidocr_onnxruntime`, `cv2`, `shapely`,
  `pyclipper`) even when it is installed, so the app is the same whatever the build machine has.
  onnxruntime stays: faster-whisper's silence filter (`vad_filter=True`) runs on it.
- **Every build drops the unused Qt pieces and `hf_xet`.** The spec filters Qt by bundle path,
  including the top-level symlinks PyInstaller adds for each framework, so none dangle. Without
  `hf_xet`, huggingface_hub downloads the Whisper model over plain HTTPS.
- `build.py` deletes the one-folder build that PyInstaller leaves beside `Marginalia.app`.

## Consequences
- The macOS app is 258 MB (106 MB `.dmg`), 40% smaller. What remains is mostly voice (PyAV,
  onnxruntime, CTranslate2, tokenizers: about 130 MB), Qt (about 55 MB) and Python itself.
- It also starts sooner: about 14 s to "Ready" against 21 s for the old build (unsigned, demo
  mode, offscreen), since RapidOCR no longer loads its models at launch.
- Only PyAV ships FFmpeg on macOS now, so the "AVFFrameReceiver is implemented in both" warning
  is gone there. The Windows build still bundles both copies.
- Two OCR engines with different output shapes; `OCR.read` normalises both, and the tests cover
  each with a fake engine, plus one test against real Vision where it is installed.
- Vision's confidences are coarse (0.3, 0.5 or 1.0), so `min_score` means less on macOS.
- A dev install on macOS that has RapidOCR but not Vision still works (RapidOCR loads second),
  but the packaged app has no OCR unless the build environment has `pyobjc-framework-Vision`.

## Alternatives considered
- **opencv-python-headless.** Byte-for-byte the same size on macOS: the FFmpeg libraries are
  in both wheels.
- **A lean download without OCR and voice, plus a full one.** 120 MB, but the default app would
  lose sharper pointing, and two builds double the release work.
- **A stub `av` module** so faster-whisper imports without PyAV (44 MB). It never decodes a file
  here, since we pass it arrays. Not done yet: it fails the moment faster-whisper touches `av`
  at import time in a new way, and voice is not the larger cost.
- **Windows.Media.Ocr on Windows.** The same trade for the Windows build, worth doing next.
