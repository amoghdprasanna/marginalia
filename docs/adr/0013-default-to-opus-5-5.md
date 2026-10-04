# 0013. Default model: Claude Opus 5.5

**Status:** Accepted, 2026-10-04. Supersedes the model choice in [0009](0009-model-defaults.md); its
effort, `max_tokens` and refusal-fallback decisions stand.

## Context
ADR 0009 picked `claude-opus-5`. Claude Opus 5.5 has since replaced it as the current Opus:
same 1M context, vision, structured outputs, effort levels and server-side fallbacks, at
$4 / $20 per million input / output tokens instead of $5 / $25 (cache reads $0.20 instead of
$0.50).

## Decision
Default `MARGINALIA_MODEL` to `claude-opus-5-5`.

What differs for us, checked against the request we send:
- Thinking cannot be disabled on Opus 5.5. We never disabled it, so nothing changes.
- Its default effort is `medium` where Opus 5 defaulted to `high`. We already send
  `effort: medium` explicitly, so behaviour does not depend on the default.
- Forced tool choice is rejected. We use no tools (structured outputs instead, ADR 0011).
- Thinking blocks are bound to the model and conversation. We don't replay thinking: each
  question is a single user turn with history folded into text.

## Consequences
- About 20% cheaper per question at the same effort, before any tuning.
- This is a choice by price and lineage, not by measurement. The first real eval run
  (`python eval/run_eval.py`, then again with `--model claude-opus-5`) should confirm that
  pointing and answer checks hold. If they don't, set `MARGINALIA_MODEL=claude-opus-5` and
  record the numbers in a new ADR.

## Alternatives considered
- **Wait for the eval set to reach 30 cases before switching.** Cleaner, but it means paying
  more meanwhile for a model that is the predecessor of this one.
- **`claude-sonnet-5-5` ($2 / $10).** Plausibly good enough for "explain this equation", and
  half the price again. That is exactly the kind of call the eval exists for; not by feel.
