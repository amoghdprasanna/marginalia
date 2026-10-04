# 0004. Points as JSON, snapped to OCR lines

**Status:** Accepted, 2026-10-02. Parsing superseded by [0011](0011-structured-outputs-and-prompt-caching.md).

## Context
An answer needs prose *and* zero to four screen targets with labels. Model coordinates are good
but not perfect; OCR boxes are exact but OCR garbles maths.

## Decision
The system prompt asks for one JSON object `{"answer": ..., "points": [...]}`. Each point has
pixel coordinates in the image it came from, and optionally the id of an OCR line. `pointing`
keeps the model's x but snaps y onto the line when the two agree, trusts the line when they
disagree, and merges markers closer than 48 px.

`brain.parse_reply` is deliberately forgiving: it strips code fences and surrounding prose,
repairs LaTeX backslashes that collide with JSON escapes (`\beta` would otherwise decode as a
backspace and "eta"), and falls back to showing raw text with no markers.

## Consequences
- One request per question, so latency stays low.
- Parsing is heuristic, so it carries a lot of tests (`tests/test_brain.py`).
- Two markers on the same target, which looked like one qubit split in two, are prevented in
  two places: the prompt asks for one point per target, and `MERGE_RADIUS` merges anyway.

## Alternatives considered
- **Structured outputs (`output_config.format` with a JSON schema):** guarantees valid JSON and
  would delete most of the lenient parser. A strong candidate for the next stage (see the
  roadmap); it needs an eval run first to confirm answer quality and latency don't regress.
- **Tool use (`point_at` tool):** valid, but splits one answer into several blocks and adds
  a round of bookkeeping for no gain in a single-turn exchange.
