"""Installing a release from inside the app: what is allowed, the download check, the swap."""

import hashlib
import io
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError

import pytest

from marginalia import BUNDLE_ID
from marginalia.selfupdate import (
    DOWNLOAD_PREFIX,
    UpdateCancelled,
    UpdateError,
    Updater,
    app_location,
    mac_swap_script,
    windows_swap_script,
)
from marginalia.updates import Asset, Release

PAYLOAD = b"new version " * 1000
DIGEST = "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()


class Download(io.BytesIO):
    def __init__(self, data=PAYLOAD, url="https://objects.githubusercontent.com/x"):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def serving(data=PAYLOAD, url="https://objects.githubusercontent.com/x", seen=None):
    def opener(request, timeout):
        if seen is not None:
            seen.append(request)
        return Download(data, url)

    return opener


def asset(name="Marginalia-0.2.0-macos.dmg", size=None, digest=DIGEST):
    return Asset(name, DOWNLOAD_PREFIX + "v0.2.0/" + name, len(PAYLOAD) if size is None else size, digest)


def release(*assets):
    return Release("0.2.0", "https://github.com/o/r/releases/tag/v0.2.0", "", {a.name: a for a in assets})


def mac_app(tmp_path, version="0.1.0", bundle=BUNDLE_ID, name="Marginalia.app"):
    app = tmp_path / name
    (app / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    (app / "Contents" / "MacOS" / "Marginalia").write_text(version)
    info = {"CFBundleIdentifier": bundle, "CFBundleShortVersionString": version}
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    return app


def mac_updater(tmp_path, **kw):
    app = mac_app(tmp_path / "Applications")
    kw = {"run": FakeMac(tmp_path), "machine": "arm64", **kw}
    return Updater(
        platform="darwin", frozen=True, executable=str(app / "Contents/MacOS/Marginalia"), pid=4242,
        workdir=tmp_path, **kw,
    )  # fmt: skip


class FakeMac:
    """hdiutil and ditto, enough to stage an app: the disk image holds `inside`."""

    def __init__(self, tmp_path, version="0.2.0", bundle=BUNDLE_ID, team="not set", new_team=None):
        self.tmp, self.version, self.bundle = tmp_path, version, bundle
        self.team, self.new_team = team, new_team or team
        self.calls = []

    def __call__(self, cmd, check=False, capture_output=False, text=False):
        self.calls.append(cmd)
        if cmd[:2] == ["hdiutil", "attach"]:
            mac_app(Path(cmd[-1]), self.version, self.bundle)
        elif cmd[0] == "ditto":
            shutil.copytree(cmd[1], cmd[2])
        elif cmd[:2] == ["codesign", "-dv"]:
            team = self.new_team if Path(cmd[2]).name.startswith(".") else self.team
            return subprocess.CompletedProcess(cmd, 0, "", f"Identifier={BUNDLE_ID}\nTeamIdentifier={team}\n")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")


# what is allowed --------------------------------------------------------------------------------


def test_app_location():
    assert app_location("/Applications/Marginalia.app/Contents/MacOS/Marginalia", "darwin").name == "Marginalia.app"
    assert app_location(str(Path("C:/Programs/Marginalia/Marginalia.exe")), "win32").name == "Marginalia"


def test_only_the_packaged_app_with_a_checksummed_installer_updates_itself(tmp_path):
    good = release(asset())
    assert mac_updater(tmp_path).problem(good) is None
    assert "Python" in Updater(frozen=False).problem(good)
    assert "Apple silicon" in mac_updater(tmp_path, machine="x86_64").problem(good)
    assert "no installer" in mac_updater(tmp_path).problem(release(asset("Marginalia-0.2.0-windows-setup.exe")))
    assert "checksum" in mac_updater(tmp_path).problem(release(asset(digest="")))


def test_a_mac_app_still_on_the_disk_image_asks_to_be_moved_first(tmp_path):
    exe = "/Volumes/Marginalia/Marginalia.app/Contents/MacOS/Marginalia"
    u = Updater(platform="darwin", machine="arm64", frozen=True, executable=exe)
    assert "Applications" in u.problem(release(asset()))


def test_windows_needs_the_installed_copy(tmp_path):
    folder = tmp_path / "Marginalia"
    folder.mkdir()
    u = Updater(platform="win32", frozen=True, executable=str(folder / "Marginalia.exe"), workdir=tmp_path)
    good = release(asset("Marginalia-0.2.0-windows-setup.exe"))
    assert "installer" in u.problem(good)
    (folder / "unins000.exe").write_bytes(b"")
    assert u.problem(good) is None


# the download ---------------------------------------------------------------------------------


def test_download_keeps_the_file_github_recorded(tmp_path):
    seen, progress = [], []
    u = mac_updater(tmp_path, opener=serving(seen=seen))
    path = u.download(asset(), tmp_path, on_progress=lambda got, total: progress.append((got, total)))
    assert path.read_bytes() == PAYLOAD
    assert seen[0].full_url.startswith(DOWNLOAD_PREFIX)
    assert progress[-1] == (len(PAYLOAD), len(PAYLOAD))


@pytest.mark.parametrize(
    ("opener", "the_asset", "says"),
    [
        (serving(b"tampered" * 100), asset(), "doesn't match"),
        (serving(), asset(size=10), "bigger"),
        (serving(url="https://evil.example/x"), asset(), "somewhere other"),
        (serving(url="http://objects.githubusercontent.com/x"), asset(), "somewhere other"),
        (serving(), Asset("x.dmg", "https://evil.example/x.dmg", 1, DIGEST), "release page"),
    ],
)
def test_download_refuses_anything_else(tmp_path, opener, the_asset, says):
    with pytest.raises(UpdateError, match=says):
        mac_updater(tmp_path, opener=opener).download(the_asset, tmp_path)


def test_a_download_that_does_not_match_is_deleted(tmp_path):
    with pytest.raises(UpdateError):
        mac_updater(tmp_path, opener=serving(b"tampered")).download(asset(size=0), tmp_path)
    assert not (tmp_path / asset().name).exists()


def test_download_failures_and_cancelling(tmp_path):
    def offline(request, timeout):
        raise URLError("no network")

    with pytest.raises(UpdateError, match="download failed"):
        mac_updater(tmp_path, opener=offline).download(asset(), tmp_path)
    with pytest.raises(UpdateCancelled):
        mac_updater(tmp_path, opener=serving()).download(asset(), tmp_path, cancelled=lambda: True)


# macOS: staging and the swap ------------------------------------------------------------------


def test_prepare_stages_the_new_app_beside_this_one_and_starts_the_swap_on_request(tmp_path):
    started = []
    u = mac_updater(tmp_path, opener=serving(), start=started.append)
    apply = u.prepare(release(asset()))
    staged = u.app.with_name(".Marginalia-0.2.0.app")
    assert (staged / "Contents/MacOS/Marginalia").read_text() == "0.2.0"
    assert started == [], "nothing is swapped until the app is ready to quit"
    apply()
    (cmd,) = started
    assert cmd[0] == "/bin/sh"
    script = Path(cmd[1]).read_text()
    assert "kill -0 4242" in script and str(staged) in script


@pytest.mark.parametrize(
    ("fake", "says"),
    [
        ({"bundle": "com.example.other"}, "different app"),
        ({"version": "0.1.9"}, "different version"),
        ({"team": "TEAM123456", "new_team": "OTHER12345"}, "same developer"),
    ],
)
def test_a_staged_app_that_is_not_the_release_is_thrown_away(tmp_path, fake, says):
    u = mac_updater(tmp_path, opener=serving(), run=FakeMac(tmp_path, **fake))
    with pytest.raises(UpdateError, match=says):
        u.prepare(release(asset()))
    assert not list(u.app.parent.glob(".Marginalia-*")), "the rejected copy is removed"
    assert not list(tmp_path.glob("marginalia-update-*")), "and so is the download"


def test_signed_apps_need_a_matching_signature(tmp_path):
    u = mac_updater(tmp_path, opener=serving(), run=FakeMac(tmp_path, team="TEAM123456"))
    u.prepare(release(asset()))
    assert u.team() == "TEAM123456" and not u.loses_permissions()
    assert any(c[:2] == ["codesign", "--verify"] for c in u.run.calls)


def test_unsigned_apps_lose_their_permissions_on_update(tmp_path):
    assert mac_updater(tmp_path).loses_permissions()


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX shell script")
def test_the_swap_waits_for_the_app_to_quit_then_replaces_and_opens_it(tmp_path):
    old, new = mac_app(tmp_path, "0.1.0"), mac_app(tmp_path, "0.2.0", name=".Marginalia-0.2.0.app")
    opened = tmp_path / "opened"
    running = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.6)"])
    script = tmp_path / "update.sh"
    script.write_text(mac_swap_script(running.pid, old, new, launch=f"printf %s >{opened}"))
    t0 = time.monotonic()
    swap = subprocess.Popen(["/bin/sh", str(script)])
    running.wait()
    assert swap.wait(timeout=10) == 0
    assert time.monotonic() - t0 >= 0.5, "it waited for the old copy to quit"
    assert (old / "Contents/MacOS/Marginalia").read_text() == "0.2.0"
    assert not new.exists() and not list(tmp_path.glob(".Marginalia-previous*"))
    assert opened.read_text() == str(old)


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX shell script")
def test_a_failed_swap_puts_the_old_app_back(tmp_path):
    old = mac_app(tmp_path, "0.1.0")
    script = tmp_path / "update.sh"
    script.write_text(mac_swap_script(999999, old, tmp_path / "missing.app", launch="true"))
    subprocess.run(["/bin/sh", str(script)], timeout=10)
    assert (old / "Contents/MacOS/Marginalia").read_text() == "0.1.0"


def test_cleanup_removes_leftovers(tmp_path):
    u = mac_updater(tmp_path)
    (tmp_path / "marginalia-update-abc").mkdir()
    mac_app(u.app.parent, name=".Marginalia-0.2.0.app")
    u.cleanup()
    assert not list(tmp_path.glob("marginalia-update-*"))
    assert [p.name for p in u.app.parent.iterdir()] == ["Marginalia.app"]


# Windows --------------------------------------------------------------------------------------


def test_windows_prepare_runs_the_installer_after_the_app_quits(tmp_path):
    folder = tmp_path / "Marginalia"
    folder.mkdir()
    (folder / "unins000.exe").write_bytes(b"")
    started = []
    u = Updater(
        platform="win32", frozen=True, executable=str(folder / "Marginalia.exe"), opener=serving(),
        start=started.append, pid=4242, workdir=tmp_path,
    )  # fmt: skip
    u.prepare(release(asset("Marginalia-0.2.0-windows-setup.exe")))()
    (cmd,) = started
    assert cmd[:2] == ["cmd.exe", "/c"]
    script = Path(cmd[2]).read_text()
    assert '"PID eq 4242"' in script and "-windows-setup.exe\" /SILENT" in script


@pytest.mark.skipif(sys.platform != "win32", reason="runs cmd.exe")
def test_the_windows_script_starts_the_installer_once_the_app_has_quit(tmp_path):
    ran = tmp_path / "ran.txt"
    setup = tmp_path / "setup.cmd"
    setup.write_text(f"@echo %* > \"{ran}\"\r\n")
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    script = tmp_path / "update.cmd"
    script.write_text(windows_swap_script(gone.pid, setup))
    subprocess.run(["cmd.exe", "/c", str(script)], timeout=30)
    deadline = time.monotonic() + 10
    while not ran.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert "/SILENT" in ran.read_text()
