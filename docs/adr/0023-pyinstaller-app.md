# 0023. The desktop app: PyInstaller, signed and notarised when credentials exist

**Status:** Accepted, 2026-10-08

## Context
"Someone else can install it" means no Python, no terminal, no `pip`. On macOS it also means a
signed and notarised app, or Gatekeeper refuses to open it, and a bundle that macOS treats as the
app asking for Screen Recording and the microphone (today it is whichever terminal you use).

## Decision
- **PyInstaller**, one spec (`packaging/marginalia.spec`) for macOS and Windows, run by
  `packaging/build.py`. A one-folder build (`onedir`), wrapped as `Marginalia.app` on macOS.
- **macOS bundle:** id `io.github.amoghdprasanna.marginalia`, `LSUIElement` (no Dock icon: the
  orb and its menu are the interface), a microphone usage string, minimum macOS 12. The icon is
  drawn by `packaging/make_icon.py` with the same painting code as the orb.
- **Signing** with the hardened runtime and three entitlements: microphone input, unsigned
  executable memory (ctypes callbacks for Carbon hotkeys are libffi closures), and disabled
  library validation (Python extension modules and Qt plugins). Then **notarisation** of the app
  and of the `.dmg` with `notarytool`, and stapling. All of it runs only when the credentials are
  set (ADR 0022, `docs/releasing.md`); without them the build is ad-hoc signed and still runs on
  the Mac that built it.
- **Extras:** the build bundles OCR and voice when installed (CI installs both). The packaged
  app calls `multiprocessing.freeze_support()` first: bundled libraries start a multiprocessing
  resource tracker, which in a frozen app re-launches the app's own executable.
- **Architecture:** CI builds on Apple silicon (`macos-14`), so the `.dmg` is arm64. Intel Macs
  can still `pip install`.

## Consequences
- About 400 MB installed with OCR and voice (onnxruntime, CTranslate2, OpenCV, PyAV, Qt).
- OpenCV (from RapidOCR) and PyAV (from faster-whisper) each bundle their own FFmpeg; macOS logs
  "Class AVFFrameReceiver is implemented in both" at startup. Harmless so far because neither
  uses FFmpeg's device capture here; it goes away if either dependency drops its copy.
- Screen Recording and Microphone are granted to Marginalia itself, so the setup check (ADR 0018)
  shows its Restart button for the packaged app.

## Alternatives considered
- **Briefcase.** Native installers and a cleaner story for signing, but it wants its own project
  layout and template, and its support for heavy binary wheels (onnxruntime, ctranslate2) is
  thinner than PyInstaller's hooks.
- **py2app.** macOS only; we would still need PyInstaller for Windows.
- **Nuitka.** Compiles to C for speed we don't need, and much slower builds.
- **Universal2 build.** Needs universal wheels for every binary dependency; onnxruntime and
  ctranslate2 don't all ship them.
