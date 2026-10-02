# 0007. Worker pool, Qt signals and request ids

**Status:** Accepted, 2026-10-02

## Context
OCR (~0.5 s), the API call (2 to 10 s) and transcription (~1 s) must not freeze the overlay. Qt
widgets may only be touched from the main thread. The user can abandon a question at any time
by closing the bubble, asking again, or following up.

## Decision
- Slow work goes to a `ThreadPoolExecutor` (3 workers). OCR starts the moment the screen is
  grabbed, so it overlaps with the user typing.
- Workers never touch widgets. Futures complete into `Bus` signals; Qt queues them onto the
  main thread.
- Each question gets an increasing `request_id` (and each recording a `listen_id`). Handlers
  drop results whose id is no longer current, so a slow answer to an abandoned question never
  overwrites a newer one.
- Timers are always given an owner (`QTimer.singleShot(ms, self, fn)`), so Qt cancels them if
  the widget goes away. An owner-less timer firing into a deleted widget was a real crash,
  found by the test suite.

## Consequences
- The UI stays responsive; cancelling is just bumping an id.
- Abandoned work still runs to completion and costs tokens. An abandoned API call is not
  cancelled.
- The executor is injected (`Services.pool`), so tests use an inline executor or a manual one
  that lets them finish requests out of order.

## Alternatives considered
- **asyncio + qasync:** cleaner cancellation, but a second event loop to integrate, and the
  blocking libraries (OCR, Whisper) would still need threads.
- **QThread per task:** more boilerplate for the same result.
