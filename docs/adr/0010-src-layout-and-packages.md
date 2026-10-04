# 0010. `src/` layout, and packages for the two big modules

**Status:** Accepted, 2026-10-04

## Context
The package sat at the repository root as `marginalia/`, with `run.py` beside it. Two modules
had outgrown one file: `ui.py` (950 lines, nine widgets) and `brain.py` (prompt, parsing, API
call and demo mode in one place). Stage 2 adds a schema, streaming and usage accounting to
the brain, which would have pushed it the same way.

Two concrete problems with the flat layout:
- **Tests imported the working tree, not the installed package.** Python puts the current
  directory on `sys.path`, so `import marginalia` found the folder whether or not it was
  installed correctly. `pyproject.toml` said `packages = ["marginalia"]`: the moment we added a
  subpackage, a built wheel would have silently left it out and every test would still pass.
- **Finding code.** "Where is the bubble?" meant scrolling a 950-line file.

## Decision
- Move the package to `src/marginalia/`. Packaging uses `packages.find(where = ["src"])`, so
  subpackages are picked up automatically. Tests only see the package once it is installed
  (`pip install -e .`), which is exactly how users get it.
- Split by reason to change, not by size:
  - `brain/`: `prompt` (what we send), `parsing` (what comes back), `claude` (the API call),
    `demo`, `types`.
  - `ui/`: `theme` and `paint` (look), `widgets` (shared controls), then one module per window:
    `askbox`, `bubble`, `chooser`, `listen`, `orb`, `overlay`.
- Each package's `__init__` re-exports its public names, so `from marginalia.brain import
  ClaudeBrain` and `from marginalia.ui import AnswerBubble` keep working. Callers don't learn the
  inner file layout.
- The small modules (`capture`, `ocr`, `pointing`, `cursor`, `voice`, `doubtlog`, `config`, `app`)
  stay flat. A package for a 20-line file is ceremony.
- `run.py` is gone: `marginalia` (the console script) and `python -m marginalia` do the same.
  `.env` is now looked up from the folder you start in, then from above the package.
- Screenshots used by the README move to `docs/images/`.

## Consequences
- A wheel built from the repo is checked in this ADR's commit to contain `brain/` and `ui/`.
- Moving files breaks `git blame` continuity a little; `git log --follow` still works per file.
- Helpers that were private to `ui.py` (`_Panel`, `_Chip`, ...) are now shared between modules,
  so they lost the underscore and live in `ui/widgets.py`.

## Alternatives considered
- **Keep the flat layout, just split files.** Fixes navigation but not the "tests pass against
  a broken wheel" trap.
- **Layer folders (`core/`, `adapters/`, `ui/`).** Mirrors `docs/architecture.md` exactly, but
  `capture.py` is half pure maths and half Qt grab, and moving every import for a 3,500-line
  app buys little. Revisit if the core grows.
