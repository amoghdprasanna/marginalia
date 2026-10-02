# 0008. Testable core, thin Qt shell, fakes over mocks

**Status:** Accepted, 2026-10-02

## Context
The app touches the screen, a microphone, the network, a GPU-less ML model, global hotkeys and
the window system. Tests that need any of those are slow, flaky, or impossible in CI.

## Decision
- **Pure core:** decisions are plain functions or small classes with no I/O: coordinate
  maths, reply parsing, point snapping, bubble placement, cursor-rest tracking
  (`cursor.RestTracker`), end-of-speech (`voice.SilenceDetector`). Widgets call them.
- **Injection at the edges:** `app.Services` bundles brain, OCR, journal, transcriber,
  recorder, screen grabber and executor. Adapters take factories (`Recorder(stream_factory)`,
  `Transcriber(model_factory)`, `ClaudeBrain(cfg, client)`).
- **Fakes, not mocks:** `tests/helpers.py` has small working stand-ins (`FakeBrain`,
  `FakeStream`, `FakeWhisper`, `ManualExecutor`). Tests assert on behaviour ("the bubble shows
  the answer"), not on which methods were called, so refactors don't break them.
- **Qt offscreen:** widget and controller tests run under pytest-qt with
  `QT_QPA_PLATFORM=offscreen`.
- **Regression tests name the bug** they pin, in their docstring.

## Consequences
- About 150 tests in under 20 s, no hardware, no network, same on CI and laptop.
- Writing the tests found five real bugs: the invalid default model id, LaTeX decoding
  (`\beta` became a backspace), journal screenshots overwriting each other within a second,
  owner-less timers crashing after widget deletion, and the bubble rendering its first
  paragraph as a bullet.
- Remaining untested code is OS glue (`grab_screen`, hotkey, `main`), checked by hand.
  Answer *quality* is measured separately by `eval/`, which costs real API calls.

## Alternatives considered
- **`unittest.mock` everywhere:** quick to write, but couples tests to call structure.
- **End-to-end GUI automation:** catches more integration issues, but is slow and flaky for
  overlays across apps; maybe later for a smoke test.
