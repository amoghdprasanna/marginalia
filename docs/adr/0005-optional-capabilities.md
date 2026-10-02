# 0005. OCR and voice are optional and degrade gracefully

**Status:** Accepted, 2026-10-02

## Context
OCR (onnxruntime, ~100 MB) and voice (Whisper models, PortAudio) are heavy, platform-sensitive
installs. The core experience, screenshot to answer, needs neither.

## Decision
They are pip extras (`.[ocr]`, `.[voice]`). Their imports happen lazily inside the adapter, and
each adapter exposes `available` plus a human-readable reason. The UI adapts: the Speak button
is disabled with the reason as its tooltip, mic buttons hide, and speaking falls back to typing.
Availability checks avoid importing (`importlib.util.find_spec`), because importing
faster-whisper costs seconds at startup.

## Consequences
- A fresh install works with three lines; capabilities are opt-in.
- CI installs only `.[dev]`, which *proves* the app and tests do not secretly depend on the
  extras.
- Every feature has two code paths (with and without), and both need tests.

## Alternatives considered
- **Hard dependencies:** simpler code, but a PortAudio build failure would block someone who
  only wanted to type.
- **Plugins discovered at runtime:** more machinery than two optional features justify.
