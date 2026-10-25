"""Install, update and uninstall the built Windows app for real (ADR 0028). Run on Windows after
packaging/build.py; the release workflow does:

    python packaging/windows/smoke_test.py

1. The installer, run silently, installs per-user, adds the Start menu entry and starts the app
   (the same [Run] entry restarts it after an update).
2. With the app running, the updater's own script (selfupdate.windows_swap_script) waits until
   the app quits, then runs the installer over it, which starts the app again.
3. The uninstaller removes the app and the "open at login" value.
"""
from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

from marginalia.autostart import RUN_KEY, RUN_VALUE
from marginalia.selfupdate import spawn, windows_swap_script

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Marginalia"
SHORTCUT = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Marginalia.lnk"
WORK = Path(tempfile.mkdtemp(prefix="marginalia-smoke-"))
# The app the installer starts inherits this: no display needed, nothing written to the runner's home.
ENV = {
    **os.environ,
    "QT_QPA_PLATFORM": "offscreen",
    "MARGINALIA_LOG_DIR": str(WORK / "journal"),
    "MARGINALIA_SETTINGS_FILE": str(WORK / "settings.json"),
    "MARGINALIA_CHECK_UPDATES": "0",
    "ANTHROPIC_API_KEY": "sk-ant-smoke-test",
}


def step(text: str) -> None:
    print(f"\n== {text}", flush=True)


def check(ok: bool, what: str) -> None:
    print(("ok    " if ok else "FAIL  ") + what, flush=True)
    if not ok:
        sys.exit(1)


def wait_for(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.5)
    return False


def app_pids() -> list[int]:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Marginalia.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True
    ).stdout
    return [int(row[1]) for row in csv.reader(io.StringIO(out)) if len(row) > 1 and row[0] == "Marginalia.exe"]


def run_value() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, RUN_VALUE)[0]
    except FileNotFoundError:
        return None


def main() -> None:
    (setup,) = (ROOT / "dist").glob("Marginalia-*-windows-setup.exe")
    print(f"installer: {setup.name}")

    step("Install")
    subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], env=ENV, check=True)
    check((APP_DIR / "Marginalia.exe").exists(), f"installed for this user in {APP_DIR}")
    check((APP_DIR / "unins000.exe").exists(), "with an uninstaller (the updater looks for it)")
    check(SHORTCUT.exists(), "with a Start menu entry")
    check(wait_for(app_pids, 60), "and the app started")
    old = app_pids()[0]
    # Stays up: it didn't crash on start (missing modules in the bundle would show here).
    time.sleep(5)
    check(old in app_pids(), f"the app is still running after 5 s (pid {old})")

    step("Update while the app runs")
    marker = APP_DIR / "_internal" / "smoke-marker.txt"
    marker.write_text("from the old install")
    script = WORK / "update.cmd"
    script.write_text(windows_swap_script(old, setup), encoding="utf-8")
    spawn(["cmd.exe", "/c", str(script)])
    time.sleep(4)
    check(marker.exists(), "the updater waits while the app is running")
    subprocess.run(["taskkill", "/PID", str(old), "/F"], capture_output=True)  # the app quitting
    check(wait_for(lambda: not marker.exists(), 120), "once it quits, the installer runs over the install")
    check(wait_for(lambda: any(p != old for p in app_pids()), 60), "and starts the app again")

    step("Uninstall")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:  # as "Open at login" would
        winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, f'"{APP_DIR / "Marginalia.exe"}"')
    for pid in app_pids():
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    subprocess.run([str(APP_DIR / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True)
    # The uninstaller hands over to a copy of itself in %TEMP% and returns at once.
    check(wait_for(lambda: not (APP_DIR / "Marginalia.exe").exists(), 120), "the app is removed")
    check(wait_for(lambda: not SHORTCUT.exists(), 30), "and its Start menu entry")
    check(wait_for(lambda: run_value() is None, 30), "and the open-at-login value")
    print("\nAll good.")


if __name__ == "__main__":
    main()
