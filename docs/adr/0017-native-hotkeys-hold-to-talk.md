# 0017. Native hotkeys on macOS, and a hold-to-talk voice key

**Status:** Accepted, 2026-10-08

## Context
Stage 3 wants a separate voice key you hold while speaking. That needs the key's *release*,
which `pynput.GlobalHotKeys` doesn't report. On macOS pynput had two more problems: its
listener sees every keystroke, so it needs the Accessibility permission, and it runs on its
own thread, where recent macOS versions abort when keyboard input-source APIs are called off
the main thread (the README's "if the hotkey crashes" note).

## Decision
- New module `hotkeys`, with two backends behind `register(combo, on_press, on_release)`,
  `start()`, `stop()`:
  - **macOS: Carbon `RegisterEventHotKey`** through `ctypes`. The system delivers
    `kEventHotKeyPressed` and `kEventHotKeyReleased` for our combos only, on the main thread,
    with no Accessibility permission (it never sees other keystrokes). Still the API that
    shortcut libraries on macOS use.
  - **Windows and X11: a `pynput.keyboard.Listener`** feeding a pure `ChordTracker`, which turns
    key downs and ups into combo press and release (exact modifier match, key repeat ignored).
- Combos keep pynput's spelling (`<ctrl>+<alt>+v`) in settings, so existing values still work.
  Every combo needs a modifier, so a hotkey can't fire while you type.
- The voice key (default Ctrl+Alt/Option+V, `MARGINALIA_VOICE_HOTKEY`) asks about where the
  mouse *is*, like the ask key. Held longer than 0.35 s, releasing it sends the question and a
  pause doesn't. A shorter tap behaves like the orb's Speak: listen until you pause. Released
  during the 140 ms capture delay counts as a tap.
- A combo that doesn't parse, or that another app already owns, is skipped with a warning; the
  other hotkey and the orb still work.

## Consequences
- macOS no longer needs Accessibility for hotkeys, which removes one permission from first-run
  setup (ADR 0018). Screen Recording and Microphone remain.
- `ctypes` against Carbon is unchecked by any type system: a wrong signature crashes rather than
  raises. It is small, and covered by a test that registers and releases a real hotkey on macOS.
- Carbon key codes are positions on a US layout; on other layouts the letter follows the
  physical key. Acceptable for a modifier chord.
- Wayland still has no global hotkeys here (Stage 5: the GlobalShortcuts portal).

## Alternatives considered
- **pynput Listener on macOS too.** One code path, but keeps the Accessibility requirement and
  the off-main-thread crash.
- **`NSEvent.addGlobalMonitorForEventsMatchingMask`** (pyobjc). Sees every key (Accessibility
  again) and can't stop the key reaching the front app.
- **Qt shortcuts.** Only work while one of our windows has focus; useless for a global hotkey.
