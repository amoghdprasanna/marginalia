"""Open Marginalia when you log in: the packaged app, on macOS and Windows (ADR 0028).

The system keeps the answer, not the settings file: a launch agent in ~/Library/LaunchAgents
on macOS, a value under the Run key on Windows. Turning it off in System Settings or Task
Manager is then the same as turning it off here, and the uninstaller can remove it.
"""
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

from . import BUNDLE_ID
from .selfupdate import app_location, in_temporary_place

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "Marginalia"  # the installer's uninstall step removes this same value


class WindowsRun:
    """One value under HKEY_CURRENT_USER's Run key."""

    def __init__(self, name: str = RUN_VALUE) -> None:
        self.name = name

    def get(self) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return winreg.QueryValueEx(key, self.name)[0]
        except FileNotFoundError:
            return None

    def set(self, value: str) -> None:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, self.name, 0, winreg.REG_SZ, value)

    def delete(self) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self.name)
        except FileNotFoundError:
            pass


class LoginItem:
    def __init__(
        self,
        *,
        platform: str = sys.platform,
        frozen: bool | None = None,
        executable: str = sys.executable,
        home: Path | None = None,
        run_key=None,
    ) -> None:
        self.platform = platform
        self.frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        self.executable = executable
        self.app = app_location(executable, platform)
        self.agent = (home or Path.home()) / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.plist"
        self.run_key = run_key if run_key is not None else WindowsRun()

    @property
    def problem(self) -> str | None:
        """Why this copy can't open at login, or None."""
        if self.platform not in ("darwin", "win32"):
            return "Not available on this system yet."
        if not self.frozen:
            return "Available in the installed app, not when run from Python."
        if self.platform == "darwin" and in_temporary_place(self.app):
            return "Move Marginalia into your Applications folder first."
        return None

    def enabled(self) -> bool:
        if not self.frozen:  # a copy run from Python never set one up
            return False
        if self.platform == "darwin":
            return self.agent.exists()
        if self.platform == "win32":
            return self.run_key.get() is not None
        return False

    def set(self, on: bool) -> None:
        """Turn it on or off. Raises OSError if the system refuses."""
        if on and self.problem:
            raise OSError(self.problem)
        if self.platform == "darwin":
            if on:
                self.agent.parent.mkdir(parents=True, exist_ok=True)
                self.agent.write_bytes(plistlib.dumps(self._agent()))
            else:
                self.agent.unlink(missing_ok=True)
        elif self.platform == "win32" and on:
            self.run_key.set(self._command())
        elif self.platform == "win32":
            self.run_key.delete()

    def refresh(self) -> None:
        """If it's on but points at another copy (the app was moved), point it at this one."""
        if self.problem or not self.enabled():
            return
        if self.platform == "darwin":
            try:
                current = plistlib.loads(self.agent.read_bytes())
            except (OSError, plistlib.InvalidFileException):
                current = None
            if current != self._agent():
                self.set(True)
        elif self.run_key.get() != self._command():
            self.set(True)

    def _agent(self) -> dict:
        return {
            "Label": BUNDLE_ID,
            # `open` starts it the way a double-click does, so macOS treats it as the app itself.
            "ProgramArguments": ["/usr/bin/open", str(self.app)],
            "RunAtLoad": True,
            "LimitLoadToSessionType": "Aqua",  # only in a graphical login
            "AssociatedBundleIdentifiers": [BUNDLE_ID],  # shown as Marginalia in Login Items
        }

    def _command(self) -> str:
        return f'"{self.executable}"'
