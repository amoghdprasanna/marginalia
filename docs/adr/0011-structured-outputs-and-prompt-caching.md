# 0011. Structured outputs for the answer envelope; cache the system prompt

**Status:** Accepted, 2026-10-04. Supersedes the parsing part of [0004](0004-points-as-json-snapped-to-ocr.md).

## Context
ADR 0004 asked for the `{"answer", "points"}` envelope in the prompt and parsed it forgivingly:
strip code fences and chatter, repair LaTeX backslashes that collide with JSON escapes
(`\beta` decoding as backspace + "eta"), accept `point`/`xy` variants and numbers as strings.
That was ~60 lines of regex and a dozen tests guarding guesses about how the model might drift.

The API can now constrain output to a JSON schema (`output_config.format`). Decoding is
constrained token by token, so the reply is valid JSON matching the schema, and string
escapes are produced by the decoder rather than by the model's sense of JSON.

## Decision
- Send `ANSWER_SCHEMA` (in `brain/prompt.py`) as `output_config.format`. Points are
  `{image: "full"|"zoom", x: int, y: int, line: int|null, label: str}`, all required.
- `parse_reply` becomes `json.loads` plus two UI limits the schema language can't express
  (at most 4 points, labels cut at 48 chars). The LaTeX repair, fence stripping and field
  variants are deleted.
- A reply can still be incomplete: `stop_reason` `max_tokens`, or a refusal partway through.
  For those, `partial_answer` pulls out the prose that did arrive. The same function decodes
  the answer while it streams (ADR 0012).
- The prompt's "reply with a single JSON object" paragraph, with its example, is replaced by
  one sentence. The schema is the contract now; the prompt only explains what the fields mean.
- Cache the system prompt: it becomes a content block with `cache_control: ephemeral`
  (5-minute TTL). Images and the question go after the breakpoint because they change.

## Consequences
- Fewer ways to fail quietly: no more "answer shown as raw JSON" when the model drifted.
- First request with a new schema pays a one-off compilation delay; the API caches compiled
  schemas for 24 hours. Changing the schema re-pays it.
- **Caching may do nothing yet.** The system prompt with the default user context is roughly
  450 to 500 tokens, and the minimum cacheable prefix on current Opus models is 512. Below the
  minimum the marker is silently ignored (no error, no charge). The eval prints
  `cache_read` tokens per case, which settles it. Even when it applies, the saving is small: the
  two screenshots are most of the input. Kept because it is free, and because it starts paying
  as soon as the prompt grows (a longer user context, few-shot examples).
- Ties us further to the Claude API's feature set (already true via `fallbacks`, ADR 0009).

## Alternatives considered
- **Keep the lenient parser alongside.** Belt and braces, but it would be untested against
  real failures that can no longer happen, and it hid real problems by "fixing" them.
- **Tool use (`point_at`) with `strict: true`.** Also schema-checked, but splits one answer
  into text plus tool blocks and can't be streamed as one piece of prose as simply.
- **`client.messages.parse()` with a Pydantic model.** Nicer types, but adds a dependency for
  five fields, and we need the raw text anyway to show a cut-off answer.
- **1-hour cache TTL.** Costs 2x to write instead of 1.25x; only worth it if questions sharing a
  prefix are 5 to 60 minutes apart, which is unknown until we look at the journal.
