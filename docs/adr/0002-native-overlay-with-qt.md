# 0002. Native overlay with PySide6

**Status:** Accepted, 2026-10-02

## Context
The app must draw transparent, click-through, always-on-top windows over *other* apps, capture
the screen, and listen for a global hotkey, on macOS first and Windows/Linux later. The core
(image maths, OCR, the model call, Whisper) is Python.

## Decision
Use Qt through PySide6 for all windows, painting the custom pieces (qubit, icons, waveform)
with `QPainter` in code.

## Consequences
- One language end to end; the ML and image libraries are native Python.
- Qt has first-class frameless, translucent and click-through window flags on all three OSes.
- Some per-OS patching is still needed (`WA_MacAlwaysShowToolWindow`, AppKit activation,
  Windows foreground tricks in `ui.bring_to_front`).
- Packaging a Python + Qt app into a signed `.app` is harder than for Swift (see roadmap).
- Painting in code means no design-tool assets, but icons stay crisp at any DPI and match the
  qubit exactly.

## Alternatives considered
- **Electron / Tauri:** good UI tooling, but transparent click-through overlays are fragile,
  and the Python core would run as a sidecar process with an IPC layer to maintain.
- **Swift/AppKit:** the best macOS citizen, but macOS only, and the Python core would need a
  bridge or a rewrite.
- **Tkinter:** no reliable per-pixel transparency or click-through.
