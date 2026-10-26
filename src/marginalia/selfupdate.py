"""Install a newer release from inside the packaged app (ADR 0028).

Download the release's installer, check it against the SHA-256 GitHub recorded when it was
uploaded, then hand over to a small script that waits for this copy to quit and puts the new one
in its place:
  macOS    the disk image's Marginalia.app replaces this bundle (a rename, on the same disk),
           then opens
  Windows  the new setup .exe runs over this install (no questions, a progress bar), then
           starts the app

Everything that touches the system (HTTP, subprocesses, starting the script) is injectable, so
the decisions here are tested without downloading or installing anything.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform as _platform
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from . import BUNDLE_ID, REPO, __version__
from .updates import Asset, Release

log = logging.getLogger(__name__)

# Where a release's files live, and the hosts GitHub hands their downloads to.
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
DOWNLOAD_HOSTS = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
CHUNK = 1 << 16
WORK_PREFIX = "marginalia-update-"


class UpdateError(Exception):
    """An update that didn't happen, in words for the person using the app."""


class UpdateCancelled(Exception):  # noqa: N818 - it is a signal, not an error
    pass


def app_location(executable: str = sys.executable, platform: str = sys.platform) -> Path:
    """The installed app: the .app bundle on macOS, the folder holding Marginalia.exe on Windows."""
    exe = Path(executable).resolve()
    return exe.parents[2] if platform == "darwin" else exe.parent  # Marginalia.app/Contents/MacOS/Marginalia


def in_temporary_place(app: Path) -> bool:
    """Run from the disk image, or from where macOS quarantines an app it hasn't seen moved (App
    Translocation): replacing that copy would update nothing you'll open next time."""
    return str(app).startswith("/Volumes/") or "AppTranslocation" in str(app)


def mac_swap_script(pid: int, old: Path, new: Path, launch: str = "/usr/bin/open") -> str:
    """Wait for `pid` to quit, swap `new` into `old`'s place (putting it back on failure), start it."""
    q = shlex.quote
    backup = old.with_name(f".{old.stem}-previous{old.suffix}")
    return f"""#!/bin/sh
# Marginalia's updater: wait for the running copy to quit, put the new one in its place, open it.
i=0
while kill -0 {pid} 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 300 ]; then rm -rf {q(str(new))}; exit 1; fi
  sleep 0.2
done
rm -rf {q(str(backup))}
mv {q(str(old))} {q(str(backup))} || exit 1
if mv {q(str(new))} {q(str(old))}; then rm -rf {q(str(backup))}; else mv {q(str(backup))} {q(str(old))}; fi
{launch} {q(str(old))}
"""


def windows_swap_script(pid: int, setup: Path, exe_name: str = "Marginalia.exe") -> str:
    """Wait for `pid` to quit, then run the installer over the install it came from.

    `ping` is the pause because `timeout` refuses to run without a console, which this has none of.
    """
    return f"""@echo off
rem Marginalia's updater: wait for the running copy to quit, then run the new installer.
set n=0
:wait
tasklist /NH /FI "PID eq {pid}" 2>nul | find /I "{exe_name}" >nul || goto run
set /a n+=1
if %n% gtr 120 exit /b 1
ping -n 2 127.0.0.1 >nul
goto wait
:run
start "" "{setup}" /SILENT /SUPPRESSMSGBOXES /NORESTART
"""


def spawn(args: list[str]) -> None:
    """Start the update script on its own, so it outlives this process."""
    devnull = subprocess.DEVNULL
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(args, creationflags=flags, stdin=devnull, stdout=devnull, stderr=devnull, close_fds=True)
    else:
        subprocess.Popen(args, start_new_session=True, stdin=devnull, stdout=devnull, stderr=devnull, close_fds=True)


class Updater:
    def __init__(
        self,
        *,
        platform: str = sys.platform,
        machine: str | None = None,
        frozen: bool | None = None,
        executable: str = sys.executable,
        opener=urllib.request.urlopen,
        run=subprocess.run,
        start: Callable[[list[str]], None] = spawn,
        pid: int | None = None,
        workdir: Path | None = None,
    ) -> None:
        self.platform = platform
        self.machine = machine or _platform.machine()
        self.frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        self.app = app_location(executable, platform)
        self.opener, self.run, self.start = opener, run, start
        self.pid = os.getpid() if pid is None else pid
        self.workdir = workdir or Path(tempfile.gettempdir())
        self._team: str | None | bool = False  # not looked up yet

    # can we? ------------------------------------------------------------------------------------

    def problem(self, release: Release) -> str | None:
        """Why this release can't be installed from inside the app, or None if it can."""
        if not self.frozen:
            return "This copy runs from Python: update it the way you installed it (git pull, or pip)."
        if self.platform == "darwin" and self.machine != "arm64":
            return "Releases are built for Apple silicon Macs; on this Mac, build the app yourself."
        asset = release.installer(self.platform)
        if asset is None:
            return "This release has no installer for this computer."
        if not asset.digest.startswith("sha256:"):
            return "This release doesn't record a checksum for its installer, so the download couldn't be checked."
        if self.platform == "darwin":
            if in_temporary_place(self.app):
                return "Move Marginalia into your Applications folder first, then update."
            if not os.access(self.app.parent, os.W_OK):
                return f"You can't change {self.app.parent}, where Marginalia is installed."
        if self.platform == "win32" and not (self.app / "unins000.exe").exists():
            return "This copy wasn't installed with the installer, so it can't update itself."
        return None

    def team(self) -> str | None:
        """The Apple developer team that signed this app, or None (unsigned, or ad-hoc signed)."""
        if self._team is False:
            self._team = self._team_of(self.app) if self.platform == "darwin" else None
        return self._team

    def loses_permissions(self) -> bool:
        """macOS ties Screen Recording, microphone and keychain access to the signature. An app without
        a developer's signature is a different app to it after every update, so it asks again."""
        return self.platform == "darwin" and self.team() is None

    # doing it -----------------------------------------------------------------------------------

    def prepare(
        self,
        release: Release,
        on_progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> Callable[[], None]:
        """Download, check and stage `release`; returns what starts the swap (call it, then quit).

        Runs on a worker thread. Raises UpdateError or UpdateCancelled.
        """
        problem = self.problem(release)
        if problem:
            raise UpdateError(problem)
        work = Path(tempfile.mkdtemp(prefix=WORK_PREFIX, dir=self.workdir))
        try:
            installer = self.download(release.installer(self.platform), work, on_progress, cancelled)
            if self.platform == "darwin":
                staged = self._stage_mac(installer, release)
                script = work / "update.sh"
                script.write_text(mac_swap_script(self.pid, self.app, staged), encoding="utf-8")
                args = ["/bin/sh", str(script)]
            else:
                script = work / "update.cmd"
                script.write_text(windows_swap_script(self.pid, installer), encoding="utf-8")
                args = ["cmd.exe", "/c", str(script)]
        except subprocess.CalledProcessError as exc:
            shutil.rmtree(work, ignore_errors=True)
            log.warning("Update step failed: %s %r", exc.cmd, exc.stderr)
            raise UpdateError(f"Installing the update failed ({Path(str(exc.cmd[0])).name} {exc.returncode}).") from exc
        except BaseException:
            shutil.rmtree(work, ignore_errors=True)
            raise
        log.info("Update to %s staged in %s", release.version, work)
        return lambda: self.start(args)

    def download(
        self,
        asset: Asset,
        dest: Path,
        on_progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        """Fetch `asset` into `dest`, and keep it only if it is the file GitHub recorded."""
        if not asset.url.startswith(DOWNLOAD_PREFIX):
            raise UpdateError("The installer isn't on Marginalia's release page, so it wasn't downloaded.")
        path = dest / Path(asset.name).name
        request = urllib.request.Request(
            asset.url, headers={"Accept": "application/octet-stream", "User-Agent": f"Marginalia/{__version__}"}
        )
        sha, got = hashlib.sha256(), 0
        try:
            with self.opener(request, timeout=30) as resp, path.open("wb") as f:
                final = urlparse(resp.geturl())
                if final.scheme != "https" or final.hostname not in DOWNLOAD_HOSTS:
                    raise UpdateError("The download was sent somewhere other than GitHub, so it was stopped.")
                while chunk := resp.read(CHUNK):
                    if cancelled is not None and cancelled():
                        raise UpdateCancelled
                    f.write(chunk)
                    sha.update(chunk)
                    got += len(chunk)
                    if asset.size and got > asset.size:
                        raise UpdateError("The download is bigger than the release says it is, so it was stopped.")
                    if on_progress is not None:
                        on_progress(got, asset.size)
        except OSError as exc:  # URLError, HTTPError, timeouts, a full disk
            raise UpdateError(f"The download failed ({exc}). Check your connection and try again.") from exc
        if f"sha256:{sha.hexdigest()}" != asset.digest.lower() or (asset.size and got != asset.size):
            path.unlink(missing_ok=True)
            raise UpdateError("The download doesn't match the file GitHub recorded, so it wasn't installed.")
        return path

    def cleanup(self) -> None:
        """Remove what an earlier update left behind (it ran, failed, or was cancelled)."""
        for old in self.workdir.glob(f"{WORK_PREFIX}*"):
            shutil.rmtree(old, ignore_errors=True)
        if self.frozen and self.platform == "darwin":
            for old in self.app.parent.glob(f".{self.app.stem}-*{self.app.suffix}"):
                shutil.rmtree(old, ignore_errors=True)

    # macOS --------------------------------------------------------------------------------------

    def _stage_mac(self, dmg: Path, release: Release) -> Path:
        """Copy the new Marginalia.app out of the disk image to beside this one, and check it."""
        staged = self.app.with_name(f".{self.app.stem}-{release.version}{self.app.suffix}")
        shutil.rmtree(staged, ignore_errors=True)
        mount = Path(tempfile.mkdtemp(prefix=WORK_PREFIX, dir=self.workdir))
        attach = ["hdiutil", "attach", str(dmg), "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mount)]
        self.run(attach, check=True, capture_output=True)
        try:
            source = mount / "Marginalia.app"
            if not source.is_dir():
                raise UpdateError("The disk image has no Marginalia.app in it.")
            self.run(["ditto", str(source), str(staged)], check=True, capture_output=True)
        finally:
            self.run(["hdiutil", "detach", str(mount), "-quiet"], check=False, capture_output=True)
            shutil.rmtree(mount, ignore_errors=True)
        try:
            self._check_bundle(staged, release)
        except BaseException:
            shutil.rmtree(staged, ignore_errors=True)
            raise
        return staged

    def _check_bundle(self, staged: Path, release: Release) -> None:
        try:
            info = plistlib.loads((staged / "Contents" / "Info.plist").read_bytes())
        except (OSError, plistlib.InvalidFileException) as exc:
            raise UpdateError("The new app is damaged (its Info.plist can't be read).") from exc
        if info.get("CFBundleIdentifier") != BUNDLE_ID:
            raise UpdateError("The disk image holds a different app, so it wasn't installed.")
        if info.get("CFBundleShortVersionString") != release.version:
            raise UpdateError(f"The disk image holds a different version, not {release.version}.")
        team = self.team()
        if team is None:
            return  # nothing to compare against: the checksum is the whole check (ADR 0028)
        verify = self.run(["codesign", "--verify", "--deep", "--strict", str(staged)], capture_output=True)
        if verify.returncode != 0 or self._team_of(staged) != team:
            raise UpdateError("The new app isn't signed by the same developer as this one, so it wasn't installed.")

    def _team_of(self, app: Path) -> str | None:
        try:
            out = self.run(["codesign", "-dv", str(app)], capture_output=True, text=True)
        except OSError:
            return None
        for line in (out.stderr or "").splitlines():  # codesign -d writes to stderr
            if line.startswith("TeamIdentifier="):
                value = line.split("=", 1)[1].strip()
                return None if value == "not set" else value
        return None
