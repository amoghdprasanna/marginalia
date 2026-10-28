"""Tell Chrome where the helper is (ADR 0030).

A native messaging host is a small JSON manifest in the browser's user folder (on Windows, a
registry value pointing at one) naming the program to run and the one extension allowed to run
it. Installing writes one per browser that's present; uninstalling removes them.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

HOST_NAME = "marginalia.browser"
# The extension's fixed id, from the public `key` in extension/wxt.config.ts.
EXTENSION_ID = "behgmlfpdfdjcbiogfngmghpbfgaagpa"

# Chrome and the Chromium browsers that read the same manifests, by their user-data folder.
_MAC = ("Google/Chrome", "Chromium", "BraveSoftware/Brave-Browser", "Microsoft Edge")
_LINUX = ("google-chrome", "chromium", "BraveSoftware/Brave-Browser", "microsoft-edge")
_WINDOWS_KEYS = (
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Chromium\NativeMessagingHosts",
    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
)


def manifest(command: Path, extension_id: str = EXTENSION_ID) -> dict:
    return {
        "name": HOST_NAME,
        "description": "Marginalia's helper for the notebook extension",
        "path": str(command),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }


def browser_dirs(home: Path | None = None, platform: str = sys.platform) -> list[Path]:
    """Each browser's NativeMessagingHosts folder, for the browsers that are installed."""
    home = home or Path.home()
    if platform == "darwin":
        base, names = home / "Library" / "Application Support", _MAC
    elif platform.startswith("linux"):
        base, names = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config"), _LINUX
    else:
        return []
    return [base / n / "NativeMessagingHosts" for n in names if (base / n).is_dir()]


def helper_command() -> Path:
    """The program Chrome should run: the app itself when installed, else the helper script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)  # app.main hands a chrome-extension:// caller to the helper
    found = shutil.which("marginalia-browser-host") or str(Path(sys.executable).parent / "marginalia-browser-host")
    return Path(found).resolve()


def install(dirs: list[Path] | None = None, command: Path | None = None) -> list[Path]:
    """Writes the manifest into every browser folder; returns the files written."""
    command = command or helper_command()
    text = json.dumps(manifest(command), indent=2) + "\n"
    written = []
    if sys.platform == "win32" and dirs is None:
        written.append(_install_windows(text))
        return written
    for folder in dirs if dirs is not None else browser_dirs():
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{HOST_NAME}.json"
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


def uninstall(dirs: list[Path] | None = None) -> list[Path]:
    removed = []
    if sys.platform == "win32" and dirs is None:
        return _uninstall_windows()
    for folder in dirs if dirs is not None else browser_dirs():
        target = folder / f"{HOST_NAME}.json"
        if target.exists():
            target.unlink()
            removed.append(target)
    return removed


def _windows_manifest_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Marginalia" / f"{HOST_NAME}.json"


def _install_windows(text: str) -> Path:
    import winreg

    target = _windows_manifest_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    for key in _WINDOWS_KEYS:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{key}\{HOST_NAME}") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(target))
    return target


def _uninstall_windows() -> list[Path]:
    import winreg

    for key in _WINDOWS_KEYS:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{key}\{HOST_NAME}")
        except OSError:
            pass
    target = _windows_manifest_path()
    if target.exists():
        target.unlink()
        return [target]
    return []


def cli(action: str) -> int:
    if action == "install":
        files = install()
        if not files:
            print("No Chrome, Chromium, Brave or Edge profile folder found."
                  " Open the browser once, then run this again.")
            return 1
        for f in files:
            print(f"Wrote {f}")
        print("Reload the Marginalia extension in chrome://extensions, then open its panel.")
        return 0
    for f in uninstall():
        print(f"Removed {f}")
    return 0
