# 0009. Model, effort and refusal fallback defaults

**Status:** Accepted, 2026-10-02

## Context
The prototype defaulted to `claude-sonnet-5-5`, which is not a real model id, so every
non-demo request failed with "model not found". It also capped output at 1500 tokens. On
current models adaptive thinking is on by default and shares that budget, so answers could be
cut off.

## Decision
- Default model `claude-opus-5` (override with `MARGINALIA_MODEL`).
- `max_tokens` 16000. Answers stay short because the prompt asks for 60 to 200 words; the
  headroom is for thinking.
- `output_config.effort = "medium"` (`MARGINALIA_EFFORT`): the main latency/depth lever for an
  interactive tool. `low` for snappier answers, `high` for derivations.
- Server-side refusal fallback: `fallbacks: "default"` with beta
  `server-side-fallback-2026-07-01`, so a safety decline is retried on Anthropic's recommended
  model. If that also declines, `stop_reason == "refusal"` becomes a friendly message instead
  of an empty bubble.
- `stop_reason == "max_tokens"` adds a visible "cut off" note.

## Consequences
- Real answers work out of the box with an API key.
- Effort and model are product decisions to tune with the eval set, not in code.
- The beta header and `fallbacks` parameter tie us to the Claude API (not Bedrock or Vertex);
  `ClaudeBrain.build_request` is the one place to change if that matters.

## Alternatives considered
- **Streaming:** better perceived latency, since text appears as it is written. Deferred to the
  next stage because the JSON envelope has to be parsed incrementally to show partial prose.
- **A cheaper model by default:** a cost/quality call to make with eval numbers, not up front.
