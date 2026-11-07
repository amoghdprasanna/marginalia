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


# Where the Linux package puts a manifest for every user, so the helper works before the app's
# first start (packaging/build.py). The per-user folders above still win when both exist.
LINUX_SYSTEM_DIRS = (
    "/etc/opt/chrome/native-messaging-hosts",  # Chrome, and Brave, which reads Chrome's
    "/etc/chromium/native-messaging-hosts",
    "/etc/opt/edge/native-messaging-hosts",
)


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


def register_app(dirs: list[Path] | None = None, command: Path | None = None, frozen: bool | None = None) -> list[Path]:
    """Point the browsers at this installed app, so nobody runs `install` (ADR 0033).

    The app calls it at every start and the Windows installer runs it once; it rewrites only a
    manifest that is missing or names another program (an older copy, a source checkout), so a
    moved app finds its way back. A copy run from Python leaves the manifests alone: the
    developer chose which helper the browser runs. Never raises: the app starts regardless.
    """
    if not (getattr(sys, "frozen", False) if frozen is None else frozen):
        return []
    command = command or helper_command()
    try:
        if sys.platform == "win32" and dirs is None:
            current = _windows_manifest_path()
            if _names(current, command) and _windows_registered():
                return []
            return install(command=command)
        folders = dirs if dirs is not None else browser_dirs()
        stale = [f for f in folders if not _names(f / f"{HOST_NAME}.json", command)]
        return install(stale, command) if stale else []
    except Exception:  # noqa: BLE001  (a read-only profile folder must not stop the app)
        return []


def _names(path: Path, command: Path) -> bool:
    """Whether the manifest at `path` already runs `command` for our extension."""
    try:
        return json.loads(path.read_text(encoding="utf-8")) == manifest(command)
    except (OSError, ValueError):
        return False


def _windows_registered() -> bool:
    import winreg

    target = str(_windows_manifest_path())
    for key in _WINDOWS_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{key}\{HOST_NAME}") as k:
                if winreg.QueryValueEx(k, "")[0] != target:
                    return False
        except OSError:
            return False
    return True


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


def check(dirs: list[Path] | None = None, hello=None) -> tuple[bool, list[str]]:
    """What a person needs to see when the panel says Claude isn't connected: each manifest,
    the program it names, the extension it allows, and whether the helper starts."""
    lines: list[str] = []
    ok = True
    folders = dirs if dirs is not None else browser_dirs()
    if dirs is None and sys.platform.startswith("linux"):
        folders = [*folders, *map(Path, LINUX_SYSTEM_DIRS)]
    found = [f / f"{HOST_NAME}.json" for f in folders if (f / f"{HOST_NAME}.json").exists()]
    if sys.platform == "win32" and dirs is None and _windows_manifest_path().exists():
        found.append(_windows_manifest_path())
    if not found:
        return False, [
            "No browser knows the helper yet. Open the Marginalia app once (it sets the helper up),"
            " or from source run: marginalia-browser-host install"
        ]
    for path in found:
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            ok = False
            lines.append(f"✗ {path}: can't be read ({exc}). Run install again.")
            continue
        program = Path(str(m.get("path", "")))
        allowed = m.get("allowed_origins", [])
        problems = []
        if not program.is_file() or not os.access(program, os.X_OK):
            problems.append(f"the program {program} is missing or not executable")
        if f"chrome-extension://{EXTENSION_ID}/" not in allowed:
            problems.append(f"it allows {allowed}, not chrome-extension://{EXTENSION_ID}/")
        ok = ok and not problems
        mark = "✓" if not problems else "✗"
        lines.append(f"{mark} {path}\n    runs {program}" + "".join(f"\n    problem: {p}" for p in problems))
    if hello is not None:
        try:
            about = hello()
            key = "found" if about.get("hasKey") else "missing: add it in Marginalia's Settings, under AI model"
            lines.append(f"✓ The helper starts. Model: {about.get('modelName')}. Claude key: {key}.")
            ok = ok and bool(about.get("hasKey"))
        except Exception as exc:  # what a person needs is the reason, whatever it is
            ok = False
            lines.append(f"✗ The helper didn't start: {exc}")
    return ok, lines


def cli(action: str) -> int:
    if action == "check":
        from .host import claude_fixer

        ok, lines = check(hello=lambda: claude_fixer()[1])
        print("\n".join(lines))
        print("All good: open the panel and press Check again." if ok else "Fix the ✗ lines above, then check again.")
        return 0 if ok else 1
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
