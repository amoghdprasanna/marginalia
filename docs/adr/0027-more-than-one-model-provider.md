# 0027. More than one model provider: Claude, OpenAI and Gemini

**Status:** Accepted, 2026-10-24. Extends [0011](0011-structured-outputs-and-prompt-caching.md),
[0013](0013-default-to-opus-5-5.md) and [0016](0016-api-key-in-keychain.md); none is superseded.

## Context
Marginalia only spoke the Claude API. Some people already pay for OpenAI or Google API access,
or want to compare answers on the same screen. Three things make "just call another API"
harder than it sounds:

1. **Pointing depends on coordinates.** We resize screenshots to exactly the size Claude would
   (ADR 0003), so the pixels it answers in are the pixels we sent. Each provider resizes images
   differently, and Gemini is trained to locate things on a 0–1000 grid over each image rather
   than in pixels.
2. **The answer is a schema-checked JSON envelope** (ADR 0011) that we decode while it streams
   (ADR 0012). Every provider must produce the same envelope, streamed.
3. **Settings, keys and the setup check** all assumed one service and one key.

## Decision
- **A `provider` setting** (`anthropic` | `openai` | `gemini`, default `anthropic`;
  `MARGINALIA_PROVIDER`). `providers.PROVIDERS` is one table of pure data per service: display
  name, key variable, keychain account, SDK module and pip extra, models. Config, the keychain,
  Settings and the setup check all read it.
- **The model follows the provider.** A model nobody chose is the provider's first. A model
  saved in the settings file that belongs to *another* provider is replaced (with a warning).
  A model named by `MARGINALIA_MODEL`, or one we don't list, is left alone: any name is allowed.
- **One brain per provider, same `ask`.** `ClaudeBrain` (Messages API), `GPTBrain` (Responses
  API) and `GeminiBrain` (generateContent) share the system prompt, the schema, `parse_reply`,
  and a small `Progress` class that turns streamed chunks into answer-so-far callbacks. The
  controller never knows which it holds; `brain_for(cfg)` picks.
- **Coordinates, per provider:**
  - Claude: unchanged (images sized to its exact resize).
  - GPT: images sent with `detail: "original"`, which current models don't rescale below
    65,535 px, so pixel answers line up the same way.
  - Gemini: the prompt asks for points, and states the cursor and OCR boxes, on its native
    0–1000 grid; `GeminiBrain` converts its points back to image pixels before returning, so
    `pointing` and everything after it is unchanged.
- **Structured output everywhere:** OpenAI `text.format` json_schema with `strict: true`,
  Gemini `response_json_schema`. The same `ANSWER_SCHEMA` already meets OpenAI's strict rules
  (every field required, `additionalProperties: false`).
- **Effort:** our five levels are OpenAI's (`low`…`max`) on current models. Gemini has
  `low`/`medium`/`high`; `xhigh` and `max` ask for `high`, and Settings says so.
- **Keys:** one keychain account per provider (`anthropic-api-key` keeps its old name, so
  existing keys survive). Each provider's environment variable still wins over the keychain.
- **SDKs as extras** (`[openai]`, `[gemini]`), imported only when that provider is used, like
  OCR and voice (ADR 0005). A missing SDK is a friendly error with the install command, in the
  bubble, in Settings and in the setup check. Release builds bundle both; `dev` installs both
  so their error classes are tested.
- **`store: false`** on OpenAI requests: screenshots may be private, and nothing needs the
  response kept on their side.
- The display name is **"OpenAI", not "ChatGPT"**: a ChatGPT subscription has no API access,
  and calling it ChatGPT invites people to look for a key they don't have.

## Consequences
- Claude-only features stay Claude-only: the refusal fallback (`fallbacks`, ADR 0009) and the
  explicit cache breakpoint. OpenAI and Gemini cache prefixes on their own, but our system
  prompt is below their minimum today, as it is for Claude (ADR 0011).
- **Pointing quality on GPT and Gemini is unmeasured.** OpenAI's own docs say its models
  struggle with precise localisation. OCR snapping (ADR 0004) helps whenever the model names a
  line id. The eval runs any provider (`--provider`) but only knows Claude prices, so their
  cost shows as unknown until someone copies the prices in.
- Model lists go stale faster with three vendors. They live in one table, and any model name
  still works by typing it into the settings file or `MARGINALIA_MODEL`.
- The app grows by the two SDKs (about 40 MB on disk before compilation, less once bundled).
- Error wording is shared: anthropic and openai SDKs have the same exception classes, so one
  mapper (`brain/errors.py`) serves both; Gemini has its own.

## Alternatives considered
- **One OpenAI-compatible client for everything** (Gemini offers an OpenAI-compatible
  endpoint). One SDK, but Gemini's compatibility layer lags its own API on structured output,
  thinking levels and image resolution, and it would still answer on the 0–1000 grid.
- **LiteLLM or a similar router.** Many providers for free, but a large dependency that
  flattens exactly the per-provider details pointing depends on (image detail, coordinate
  grid, schema dialect), and another layer between us and each SDK's errors.
- **Raw HTTP with httpx** instead of the SDKs. No new dependencies, but we'd own SSE parsing,
  retries and error mapping for two more APIs. The SDKs are optional extras anyway.
- **Infer the provider from the model name** (`gpt-` → OpenAI). No new setting, but it breaks
  for fine-tunes, dated snapshots and future names, and Settings still needs a key per service.
- **Pixels for Gemini too**, to keep one prompt. Simpler, but asks the model to work against
  its training; the 0–1000 grid is what Google documents for locating things.
