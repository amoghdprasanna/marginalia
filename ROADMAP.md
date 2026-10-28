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

## Stage 3: Everyday product ✅
Goal: a tool you open every day without the terminal.
- [x] Fixed first: a stale listen timer hid newer questions; cancelling a question left a hidden
      thread and a spinning orb; quit waited on busy workers; the orb could be lost off-screen;
      capture errors showed on the wrong screen; bad settings values crashed or failed every question
- [x] Settings window (model, effort, hotkeys, voice model) over a settings file; env still wins (ADR 0015)
- [x] API key in the system keychain, not a plain-text file (ADR 0016)
- [x] First-run setup check with fix-it buttons (Screen Recording, Microphone, API key) (ADR 0018)
- [x] Separate voice hotkey (hold to talk); native hotkeys on macOS, no Accessibility needed (ADR 0017)
- [x] Journal browser: search past questions, reopen a thread with its screenshot (ADR 0019)

## Stage 4: Distribution ✅ (signing waits on you)
Goal: someone else can install it.
- [x] macOS `.app` and `.dmg` with PyInstaller; signs, notarises and staples when credentials exist (ADR 0023)
- [ ] **You:** an Apple Developer ID and the six repository secrets in `docs/releasing.md`;
      until then builds are ad-hoc signed and only open on the Mac that built them
- [x] Update check: once a day, announce a newer release, download from the menu (ADR 0021)
- [x] Windows installer, open at login, and **Update now** in the app, checked against GitHub's
      SHA-256 of the installer (ADR 0028); Sparkle-style signed updates once builds are signed
- [x] Structured logs: `logging` instead of `print`, JSON lines in `<log dir>/logs` (ADR 0014)
- [x] Crash reports kept locally; opt-in reporting as a GitHub issue you review (ADR 0020)
- [x] Release process: SemVer, `CHANGELOG.md`, `scripts/release.py`, tag-triggered builds (ADR 0022)

## Stage 5: Platforms ✅ (needs a hands-on check)
- [x] Windows: CI, microphone consent check, taskbar icon, UTF-8 file handling, `.zip` build
- [x] Wayland: Screenshot and GlobalShortcuts portals, windows through XWayland (ADR 0024)
- [ ] **You (or a tester):** first real run on Windows, GNOME and KDE Wayland; tests use fakes there

## Stage 6: Notebooks in the browser (in progress)
Goal: help with a Jupyter notebook open in Chrome (UMD's cluster through Open OnDemand), from its
real cells, not a screenshot. See ADR 0029.
- [x] Chrome extension in `extension/` (WXT, React, strict TypeScript), asks only for UMD and
      local Jupyter, once
- [x] Reads the open notebook through Jupyter's own app object; lists cells that raised, with
      where and why; *Go to cell*; updates as cells run; survives reloads
- [x] Ket in the panel and the toolbar icon (now an original lamb with a Bloch-sphere bell)
- [x] Unit tests and an e2e suite against real Notebook 7.6.3 servers; CI runs both
- [x] Turned on `expose_app_in_browser` on hepcms; the panel read a real notebook there
- [x] Fix with Claude through a desktop helper over native messaging (ADR 0030): a proposed change
      as a diff, applied only when you press Apply, with Undo; stale edits refused
- [x] Panel rebuilt to Lemma's standard: light and dark, compact cards, status bar
- [ ] **You:** reload the extension and try Fix with Claude on the hepcms notebook
- [ ] Tests: pytest + testbook for the notebook's functions, and a Playwright "runs clean" check
      in its own browser profile
