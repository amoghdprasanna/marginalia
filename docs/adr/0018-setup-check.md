# 0018. A setup check with fix-it buttons

**Status:** Accepted, 2026-10-08

## Context
On macOS a missing permission fails quietly: without Screen Recording the screenshot comes back
blank, and the user finds out after asking a question. The README told people which panes to
visit; a product should check for itself and take you there.

## Decision
- `permissions.run_checks(cfg, probes, ...)` returns a list of `Check(key, title, status,
  detail, action, required)`: API key, Screen Recording (macOS; a note on Wayland), Microphone,
  Shortcuts, OCR. It is pure; the OS is asked through injected **probes**.
- `MacProbes` asks the OS directly:
  - Screen Recording: `CGPreflightScreenCaptureAccess` / `CGRequestScreenCaptureAccess`
    (CoreGraphics via `ctypes`).
  - Microphone: `AVCaptureDevice authorizationStatusForMediaType:` / `requestAccess...`
    (AVFoundation through pyobjc, which pynput already installs on macOS).
  - "Fix" requests the permission (the system prompt appears the first time) and opens the
    right System Settings pane.
  - Accessibility is no longer needed (ADR 0017), so it isn't checked.
- `SetupWindow` shows the checks with a coloured dot and a button where there is something to
  fix, "Check again", and "Restart" for the packaged app. It names the app macOS actually asks
  about (from a terminal that is iTerm or Terminal, not Marginalia) and says to restart it.
- When: on first run (no settings file yet), and at any launch where a *required* check is
  missing. Optional things (voice, OCR) never force it open. Always available from the orb menu.
  Saving Settings refreshes it, so pasting a key turns its row green.

## Consequences
- The README's permissions paragraph shrinks to "the setup check walks you through it".
- macOS reports Screen Recording for the *process's responsible app*; a grant only takes
  effect after that app restarts. The window says so instead of pretending to fix it live.
- Windows and Linux mostly report "can't check from here"; the microphone row on Windows opens
  the privacy page.

## Alternatives considered
- **Try a screenshot and see if it's blank.** That is how we found out before; it can't tell
  "no permission" from "a black slide", and it can't prompt.
- **Check every launch and always show the window.** Noise for the common case. First run plus
  "something required is missing" covers it.
