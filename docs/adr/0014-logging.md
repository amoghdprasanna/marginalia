# 0014. Log with `logging`: console lines, JSON lines in a file

**Status:** Accepted, 2026-10-08

## Context
Every message went through `print("[marginalia] ...")`. That was fine for a terminal tool, but
the next stages take the terminal away (a settings window, then a `.app` with no console), and
a bug report needs more than what scrolled past: when it happened, which model, how long the
answer took. Prints also can't be filtered by level, and tests had to scrape stdout.

## Decision
- Every module logs through `logging.getLogger(__name__)`, so all records sit under the
  `marginalia` logger. `logs.setup_logging()` owns the handlers; no module configures logging.
- Two handlers:
  - **Console**, `[marginalia] message`, at `MARGINALIA_LOG_LEVEL` (default `info`). Looks
    exactly like the old prints.
  - **File**, `<log dir>/logs/marginalia.jsonl`, everything from DEBUG up, one JSON object per
    line, rotated at 1 MB with 3 backups. Structured fields go in with `extra=` and become JSON
    keys (each answer logs model, timings, token counts, point and OCR-line counts).
- `main` sets up the console first, so problems reading the config are reported, then adds
  the file once the config says where the log folder is.
- Tests assert on `caplog.text`; a conftest fixture turns on DEBUG for `marginalia` and drops
  handlers a test added.

## Consequences
- The log file is the thing to attach to a bug report, and the base for opt-in crash reports.
- No question or answer text is logged (the journal already has it, and logs get shared);
  only metrics. Keep it that way.
- This pulls the "structured logs" item forward from Stage 4.

## Alternatives considered
- **structlog / loguru.** Nicer APIs, but a dependency for what 60 lines of stdlib do, and
  third-party libraries (anthropic, httpx) log through stdlib anyway.
- **Plain-text log file.** Readable, but every later tool (crash reports, a "slow answers"
  query) would have to parse it. JSON lines are still greppable.
- **Console only, with a `--log-file` flag.** The case where you need a log is the one where you
  didn't think to turn it on.
