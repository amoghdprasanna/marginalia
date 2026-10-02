# 0003. Resize screenshots to the API's exact size ourselves

**Status:** Accepted, 2026-10-02

## Context
The model answers "point here" in pixel coordinates *of the image it saw*. If the API silently
downsizes a 2880x1800 screenshot, its coordinates refer to an image we never had, and markers
land in the wrong place. Retina screens make this worse: logical, physical and model pixels
all differ.

## Decision
`capture.resized_size` reimplements the API's documented resize rule (long-edge and token
limits on 28 px patches). We resize to exactly that size before sending, so the API never
rescales, and keep the scale factors in `Prepared` to map answers back. A second image, a
close-up around the cursor, gives the model more pixels where the question usually is.

## Consequences
- Pointing is exact up to rounding (tests assert the cursor round-trips within 2 px).
- If Anthropic changes the resize rule, pointing drifts silently. `tests/test_capture.py`
  pins the rule; the eval set (`eval/`) catches drift in real answers.
- The prototype also sent an undocumented `transformations` field on image blocks to make
  oversize images fail loudly. It is not in the API docs, so every request failed once and was
  retried without it. Removed; our own resizing is the guarantee.

## Alternatives considered
- **Send full resolution, let the API resize, scale answers by the ratio:** depends on knowing
  the API's exact rounding anyway, and loses control of the zoom image.
- **Ask for normalised 0-1 coordinates:** models are measurably less precise with these than
  with pixel coordinates in the image they see.
