"""What the app needs from the system, whether it has it, and how to fix it (ADR 0018).

`run_checks` is pure: the probes that ask the OS are injected, so the list of checks, their
wording and their fix-it actions are tested on any platform. `MacProbes` is the real thing.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field

from .config import Config

log = logging.getLogger(__name__)

OK, MISSING, UNKNOWN, OFF = "ok", "missing", "unknown", "off"

SETTINGS_URLS = {
    "screen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "microphone": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    "windows_microphone": "ms-settings:privacy-microphone",
}


@dataclass
class Check:
    key: str
    title: str
    status: str  # ok | missing | unknown | off
    detail: str
    action: str | None = None  # button label; the window asks the probes to perform it
    required: bool = True


class NoProbes:
    """Platforms with nothing to ask: everything is allowed or can't be known."""

    def screen_recording(self) -> bool | None:
        return None

    def microphone(self) -> str:
        return "unknown"  # authorized | denied | not_determined | restricted | unknown

    def request_screen_recording(self) -> None:
        pass

    def request_microphone(self) -> None:
        pass

    def open_settings(self, pane: str) -> bool:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        url = SETTINGS_URLS.get(pane)
        return bool(url) and QDesktopServices.openUrl(QUrl(url))


class MacProbes(NoProbes):
    """CoreGraphics for Screen Recording (ctypes), AVFoundation for the microphone (pyobjc)."""

    MIC_STATUS = {0: "not_determined", 1: "restricted", 2: "denied", 3: "authorized"}

    def _cg(self):
        import ctypes

        cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        return cg

    def _capture_device(self):
        import objc

        objc.loadBundle("AVFoundation", {}, bundle_path="/System/Library/Frameworks/AVFoundation.framework")
        return objc.lookUpClass("AVCaptureDevice")

    def screen_recording(self) -> bool | None:
        try:
            return bool(self._cg().CGPreflightScreenCaptureAccess())
        except Exception as exc:  # noqa: BLE001
            log.debug("Screen Recording check failed: %s", exc)
            return None

    def request_screen_recording(self) -> None:
        try:
            self._cg().CGRequestScreenCaptureAccess()  # first time: the system prompt; later: nothing
        except Exception as exc:  # noqa: BLE001
            log.debug("Screen Recording request failed: %s", exc)

    def microphone(self) -> str:
        try:
            status = self._capture_device().authorizationStatusForMediaType_("soun")  # AVMediaTypeAudio
            return self.MIC_STATUS.get(int(status), "unknown")
        except Exception as exc:  # noqa: BLE001
            log.debug("Microphone check failed: %s", exc)
            return "unknown"

    def request_microphone(self) -> None:
        try:
            self._capture_device().requestAccessForMediaType_completionHandler_("soun", lambda granted: None)
        except Exception as exc:  # noqa: BLE001
            log.debug("Microphone request failed: %s", exc)


def _read_registry(hive: str, path: str, name: str) -> str | None:
    import winreg

    root = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}[hive]
    try:
        with winreg.OpenKey(root, path) as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return None


class WindowsProbes(NoProbes):
    """Windows keeps microphone consent in the registry: a machine-wide switch, a per-user switch,
    and one for desktop (non-Store) apps like us. Any "Deny" blocks us."""

    MIC = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

    def __init__(self, read=_read_registry) -> None:
        self.read = read

    def microphone(self) -> str:
        values = [
            self.read("HKLM", self.MIC, "Value"),
            self.read("HKCU", self.MIC, "Value"),
            self.read("HKCU", self.MIC + "\\NonPackaged", "Value"),
        ]
        if "Deny" in values:
            return "denied"
        if values[1] is None and values[2] is None:
            return "unknown"
        return "authorized"


def default_probes():
    if sys.platform == "darwin":
        return MacProbes()
    if sys.platform == "win32":
        return WindowsProbes()
    return NoProbes()


def host_app() -> str:
    """Who macOS asks about: the terminal you started from, or Marginalia itself when packaged."""
    if getattr(sys, "frozen", False):
        return "Marginalia"
    term = os.environ.get("TERM_PROGRAM", "")
    return {"Apple_Terminal": "Terminal", "iTerm.app": "iTerm", "vscode": "Visual Studio Code"}.get(
        term, term or "your terminal app"
    )


def run_checks(cfg: Config, probes, voice_problem: str | None = None, ocr_available: bool | None = None) -> list[Check]:
    """Everything worth checking, in the order to fix it."""
    checks: list[Check] = []
    who = host_app()

    if cfg.demo:
        demo = "Demo mode: canned answers, no key needed."
        checks.append(Check("api_key", "Claude API key", OK, demo, required=False))
    elif cfg.api_key:
        where = {"keychain": "in your keychain", "env": "from ANTHROPIC_API_KEY"}.get(cfg.sources.get("api_key"), "")
        checks.append(Check("api_key", "Claude API key", OK, f"Set {where}.".replace(" .", ".")))
    else:
        need = "Needed for real answers. Paste one in Settings."
        checks.append(Check("api_key", "Claude API key", MISSING, need, "Open Settings"))

    if sys.platform == "darwin":
        screen = probes.screen_recording()
        if screen:
            checks.append(Check("screen", "Screen Recording", OK, "Marginalia can see your screen."))
        else:
            checks.append(
                Check(
                    "screen",
                    "Screen Recording",
                    UNKNOWN if screen is None else MISSING,
                    f"Needed to read your screen. Allow {who}, then restart it.",
                    "Allow…",
                )
            )
    elif sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        checks.append(
            Check(
                "screen",
                "Screen capture",
                UNKNOWN,
                "Wayland: screenshots go through the desktop portal, which may ask you to allow it. "
                "Shortcuts need a desktop with the GlobalShortcuts portal (KDE, GNOME 48+).",
            )
        )

    if not cfg.voice_enabled:
        checks.append(Check("microphone", "Microphone", OFF, "Voice is turned off in Settings.", required=False))
    elif voice_problem:
        checks.append(Check("microphone", "Voice", MISSING, voice_problem, required=False))
    else:
        mic = probes.microphone()
        if mic == "authorized":
            checks.append(Check("microphone", "Microphone", OK, "Ready for spoken questions.", required=False))
        elif mic == "not_determined":
            checks.append(
                Check("microphone", "Microphone", MISSING, "Asked the first time you speak, or now.", "Allow…", False)
            )
        elif mic in ("denied", "restricted"):
            checks.append(
                Check("microphone", "Microphone", MISSING, f"Turned off for {who}. Turn it on to ask by voice.",
                      "Open Settings…", False)  # fmt: skip
            )
        else:
            detail = "Can't check from here; speak once to find out."
            action = "Open Settings…" if sys.platform == "win32" else None
            checks.append(Check("microphone", "Microphone", UNKNOWN, detail, action, False))

    if not cfg.hotkey_enabled:
        keys = "Off; use the orb."
    elif sys.platform == "darwin":
        keys = "On. No extra permission needed."
    else:
        keys = "On."
    checks.append(Check("hotkeys", "Shortcuts", OK if cfg.hotkey_enabled else OFF, keys, required=False))
    if ocr_available is not None:
        checks.append(
            Check(
                "ocr",
                "On-screen text (OCR)",
                OK if ocr_available else OFF,
                "Sharper pointing at small text." if ocr_available else "Optional: pip install 'marginalia[ocr]'.",
                required=False,
            )
        )
    return checks


def needs_attention(checks: list[Check]) -> bool:
    return any(c.required and c.status in (MISSING, UNKNOWN) and c.action for c in checks)


@dataclass
class Fixer:
    """Performs a check's action through the probes. `open_settings_window` comes from the controller."""

    probes: object
    open_settings_window: object = None
    opened: list[str] = field(default_factory=list)

    def fix(self, check: Check) -> None:
        if check.key == "api_key" and self.open_settings_window is not None:
            self.open_settings_window()
        elif check.key == "screen":
            self.probes.request_screen_recording()
            self._open("screen")
        elif check.key == "microphone":
            if check.action == "Allow…":
                self.probes.request_microphone()
            else:
                self._open("windows_microphone" if sys.platform == "win32" else "microphone")

    def _open(self, pane: str) -> None:
        self.opened.append(pane)
        self.probes.open_settings(pane)
