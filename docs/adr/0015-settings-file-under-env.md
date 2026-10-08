# 0015. A settings file, layered under environment variables

**Status:** Accepted, 2026-10-08

## Context
Every setting lived in environment variables, usually from a `.env` file in the folder you
started from. That works from a terminal and nowhere else: a packaged app (Stage 4) has no
working folder you chose, and a settings window has nowhere to write to.

## Decision
- A JSON file in the platform's per-user config folder:
  `~/Library/Application Support/Marginalia/settings.json` (macOS),
  `%APPDATA%\Marginalia\settings.json` (Windows), `$XDG_CONFIG_HOME/marginalia/settings.json`
  (Linux). `MARGINALIA_SETTINGS_FILE` points elsewhere (tests use it).
- Layers, each overriding the one before: **defaults < settings file < environment < command
  line**. Environment variables keep working exactly as before.
- `config.SETTINGS` is one table of `Setting(key, env var, type, default, choices)`. Parsing,
  validation, the settings file and the Settings window all read it, so adding a setting is one
  line. A bad value from any layer falls back to the default with a warning naming its source.
- `Config.sources` records where each value came from. The Settings window shows a field set by
  an environment variable as locked ("set by MARGINALIA_EFFORT"), instead of silently ignoring
  your edit.
- Writes merge into the existing file and keep unknown keys (an older version won't erase a
  newer version's settings), via a temp file and `os.replace`, so a crash can't truncate it.
- No settings file means first run; the app uses that to show the setup window once (ADR 0018).

## Consequences
- The `.env` workflow and the eval harness are unchanged.
- An environment variable left in a shell profile will override the window. The lock makes that
  visible rather than mysterious.

## Alternatives considered
- **Settings file over environment.** Then the window always wins, but a one-off
  `MARGINALIA_EFFORT=low marginalia` stops working, and so does every existing `.env`.
- **`QSettings`.** Native storage (plist, registry), but opaque to read and diff, awkward to
  test without Qt, and it would put Qt into the pure config layer (ADR 0008).
- **TOML.** Nicer to hand-edit, but the standard library reads it and can't write it; the file
  is meant to be written by the window, not by hand.
