# Changelog

Notable changes, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/),
and versions follow [Semantic Versioning](https://semver.org/). `python scripts/release.py X.Y.Z`
turns "Unreleased" into a version (see `docs/releasing.md`).

## [Unreleased]

### Added
- Settings window (right-click the orb): model, effort, shortcuts, voice, OCR, journal folder;
  changes apply at once. Settings live in a per-user file; environment variables still win.
- The API key is kept in the system keychain.
- First-run setup check with fix-it buttons for Screen Recording, the microphone and the API key.
- Hold-to-talk voice shortcut (Ctrl+Alt+V): hold and speak, let go to ask; tap to talk until you pause.
- Journal browser: search past questions, reopen a thread with its screenshot and ask more about it.
- JSON-lines log file in `<log dir>/logs`.
- Crash reports are kept locally; optionally, offered as a pre-filled GitHub issue you review.
- A daily check for new releases (can be turned off).
- A packaged macOS app (`packaging/`), with signing and notarisation when credentials are set.

### Changed
- macOS shortcuts use the system hotkey API: no Accessibility permission, and no crash from
  keyboard input sources being read off the main thread.

### Fixed
- An old "Didn't catch that" message could hide a newer spoken question, which was then lost.
- Cancelling a new question left the previous thread alive but hidden, so the next question
  carried its history; the orb could also keep spinning forever.
- Quitting waited for a speech-model download or an abandoned answer to finish.
- The orb could be dragged off-screen or stranded on an unplugged monitor.
- A screen-capture error was shown on the previous question's monitor.
- A bad value in `MARGINALIA_MAX_TOKENS` crashed startup; a typo in `MARGINALIA_EFFORT` failed
  every question.

## [0.1.0] - 2026-10-04

### Added
- The overlay: ask about the screen by shortcut or the orb, by typing or by voice; answers in a
  bubble with markers that fly to what the answer talks about; follow-ups; a Markdown journal.
- Structured outputs for the answer, streamed into the bubble as it is written.
- OCR snapping for precise pointing; local Whisper transcription.
- Eval harness for pointing, content, speed and cost; real questions saved as eval cases.
- Tests (unit, widget, integration) and CI on Linux and macOS; ADRs 0001 to 0013.

[Unreleased]: https://github.com/amoghdprasanna/marginalia/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/amoghdprasanna/marginalia/releases/tag/v0.1.0
