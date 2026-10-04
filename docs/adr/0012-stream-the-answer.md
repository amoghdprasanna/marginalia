# 0012. Stream the answer into the bubble

**Status:** Accepted, 2026-10-04

## Context
A question took several seconds with nothing but "Reading your screen..." on show. Most of
that wait is the model writing; the first words exist long before the last. ADR 0009 deferred
streaming because the reply is a JSON envelope: you can't show raw `{"answer": "The...` to a
reader, and a JSON parser can't read half a document.

## Decision
- `ClaudeBrain.ask` uses `client.beta.messages.stream(...)` and takes an optional
  `on_text(text)` callback. After each chunk, `parsing.partial_answer` decodes the `"answer"`
  string so far (escapes decoded only once complete, so the text never shows half a `é`).
  `on_text` gets the whole answer-so-far, not a delta, so a dropped redraw loses nothing.
- Points stay non-streaming: markers fly when the reply is complete. Half a points array is not
  worth animating, and the answer prose comes first in the schema anyway.
- Threads (ADR 0007 still holds): `on_text` runs on the worker thread and only emits a `Bus`
  signal. The controller keeps the newest text and redraws at most every 50 ms
  (`PARTIAL_MS`), because re-rendering Markdown per token is wasted work.
- Ordering: the final answer stops the redraw timer, so a queued partial can never paint over
  it. Partials carry the request id, like answers, so an old question's words are dropped.
- Cancelling: if `on_text` sees that its request is stale (bubble closed, new question), it
  raises `Cancelled`. That exits the `with stream` block, which closes the HTTP connection, so
  the model stops writing and we stop paying for an answer nobody will read.
- While streaming the bubble shows "Writing...", hides Copy and the follow-up field, follows
  the newest words when it overflows, and slides up rather than off the bottom of the screen.
  On completion it shows the usual footer, now with "first words Xs, done Ys".
- `DemoBrain` streams its canned reply word by word, so `--demo` shows the behaviour too.

## Consequences
- Time to first words becomes the latency that matters; the eval records it (`first_text`).
- The bubble may move once more when the answer completes, because its final position keeps
  clear of the markers, which are only known then.
- A refusal can now arrive after some text has been shown. The error replaces it.
- Streaming also removes the SDK's non-streaming timeout guard as a concern if `max_tokens`
  is raised a lot.

## Alternatives considered
- **Stream plain text, ask for points in a second call.** Simplest to render, but two calls
  double the image tokens and the points would arrive late.
- **Prose first, then a fenced JSON block for points.** Loses the schema guarantee (ADR 0011).
- **A general incremental JSON parser (e.g. `jiter` partial mode).** Handles any shape, but we
  need exactly one string field, and 40 lines with tests are easier to reason about than a new
  dependency's partial-mode semantics.
- **Emit deltas instead of the whole text.** Less data across threads, but then every dropped or
  coalesced signal corrupts the text. The whole answer is a few KB.
