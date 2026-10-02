# Roadmap

Each stage ends with something you can use, and with its decisions written down as ADRs.

## Stage 0: Prototype ✅
Overlay, screenshot to answer with markers, OCR snapping, journal, demo mode, voice input.

## Stage 1: Engineering foundation ✅
- git history, `pyproject.toml` with `ocr` / `voice` / `dev` extras
- Testable core with injectable services; ~150 tests, 88% line coverage, offscreen Qt
- CI on Linux and macOS (lint and tests, no optional extras)
- Architecture overview and ADRs 0001 to 0009
- Fixed: invalid default model, refusal handling, LaTeX decoding, journal collisions, timer crash

## Stage 2: Answer quality and speed (proposed next)
Goal: answers you trust, faster.
- [ ] Grow `eval/cases` to 30+ real cases from your own reading (ask, save, label)
- [ ] Baseline the eval: pointing hit rate, must-mention rate, latency, cost per question
- [ ] Structured outputs for the answer envelope; delete most of the lenient parser (ADR 0004)
- [ ] Stream the answer into the bubble as it is written
- [ ] Prompt caching for the system prompt
- [ ] Tune effort and model with the numbers, not by feel

## Stage 3: Everyday product
Goal: a tool you open every day without the terminal.
- [ ] Settings window (model, effort, hotkeys, voice model) instead of `.env`
- [ ] API key in the macOS Keychain, not a plain-text file
- [ ] First-run permission checks with fix-it buttons (Screen Recording, Accessibility, Microphone)
- [ ] Separate voice hotkey (hold to talk)
- [ ] Journal browser: search past questions, reopen a thread with its screenshot

## Stage 4: Distribution
Goal: someone else can install it.
- [ ] Signed, notarised macOS `.app` (Briefcase or PyInstaller)
- [ ] Auto-update
- [ ] Opt-in crash reporting and structured logs (`logging` instead of `print`)
- [ ] Release process: versioning, changelog, tagged builds from CI

## Stage 5: Platforms
- [ ] Windows polish and CI
- [ ] Wayland: portal-based capture and hotkeys
