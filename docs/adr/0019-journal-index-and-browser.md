# 0019. A journal index, and a browser that reopens threads

**Status:** Accepted, 2026-10-08

## Context
Every answer was appended to a dated Markdown page with its screenshot. Good to read, poor to
search, and there was no way back into a conversation: a follow-up always re-captured the live
screen, which has moved on by the time you revisit last week's paper.

## Decision
- **Index.** `DoubtLog.add` also appends one JSON line per answer to `doubts/index.jsonl`: id
  (the screenshot stamp), time, question, answer, model, shot path, **thread id**, the logical
  screen geometry and cursor, and the points the markers flew to. The Markdown page is unchanged
  and stays the human-readable record.
- **Threads.** The controller gives a thread the id of its first answer and passes it with
  every follow-up; ending the thread (Esc, close, cancelling a new question) clears it.
- **Backfill.** Pages written before the index are parsed once into it, so old questions appear
  (without geometry or points). A torn last line after a crash is skipped.
- **`journal.Journal`** (pure, no Qt) lists threads newest first, searches question and answer
  text, and rebuilds a `Snapshot` from a saved shot. The shot is the resized image the model saw,
  so it maps onto the original logical screen at a different scale; `Snapshot` only needs the
  ratio, so pointing math is unchanged.
- **Browser** (orb menu, Journal…): search, thread list, the screenshot with the last answer's
  markers drawn on it, the conversation, and "Ask more about this screenshot". That follow-up is
  answered about the **saved** screenshot with the thread's history (OCR re-run on it if
  available), streamed into the window, and appended to the same thread.
- The window reads the journal directly (read-only data) but never calls the model: it emits
  `followup(thread, question)` and the controller answers, like every other window (ADR 0008).

## Consequences
- Reopened follow-ups see the 1568 px shot rather than the full-resolution screen, so very small
  text is less legible than live. Saving full-resolution shots would cost several MB per question.
- The saved shot already has the cursor ring; asking again draws a second ring in the same place.
- The index is append-only JSON lines: no locking, no migrations, cheap to rebuild from pages.

## Alternatives considered
- **SQLite with full-text search.** Faster at thousands of entries and real FTS, but a schema to
  migrate, and the journal is one person's questions: a linear scan of a few thousand lines is
  instant. Revisit if search ever feels slow.
- **Parse the Markdown every time.** No second file, but the format would have to carry thread
  ids, geometry and points, and parsing prose is fragile.
- **Reopen onto the live overlay** (markers on the real screen). Wrong as soon as the screen has
  changed, which is the whole reason to reopen from the journal.
