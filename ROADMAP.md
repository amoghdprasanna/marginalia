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

## Stage 1.5: Project layout ✅
- `src/` layout; `brain/` and `ui/` split into packages by reason to change (ADR 0010)
- `run.py` replaced by the `marginalia` command; CI checks the built wheel contains every subpackage

## Stage 2: Answer quality and speed (in progress)
Goal: answers you trust, faster.
- [x] Structured outputs for the answer envelope; lenient parser deleted (ADR 0011)
- [x] Stream the answer into the bubble as it is written; cancel abandoned streams (ADR 0012)
- [x] Prompt caching for the system prompt (ADR 0011; may be below the 512-token minimum, the eval will tell)
- [x] Eval measures time to first words, total time, tokens and cost; `--model/--effort/--repeat`
- [x] `MARGINALIA_SAVE_CASES=1` saves real questions as ready-to-label eval cases
- [x] Default model `claude-opus-5-5` (ADR 0013), to be confirmed by the first eval run
- [ ] **You:** grow `eval/cases` to 30+ real cases from your own reading (save, label, copy)
- [ ] Baseline run on those cases; record the numbers in an ADR
- [ ] Effort sweep (`low`/`medium`/`high`) and a `claude-sonnet-5-5` comparison; pick defaults by the numbers

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
