"""Opening at login: a launch agent on macOS, a Run value on Windows."""

import plistlib
import sys

import pytest

from marginalia import BUNDLE_ID
from marginalia.autostart import LoginItem, WindowsRun

MAC_EXE = "/Applications/Marginalia.app/Contents/MacOS/Marginalia"
WIN_EXE = r"C:\Users\a\AppData\Local\Programs\Marginalia\Marginalia.exe"


class FakeRun:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def delete(self):
        self.value = None


def mac(tmp_path, exe=MAC_EXE, frozen=True):
    return LoginItem(platform="darwin", frozen=frozen, executable=exe, home=tmp_path)


def test_mac_writes_and_removes_a_launch_agent_that_opens_the_app(tmp_path):
    item = mac(tmp_path)
    assert item.problem is None and not item.enabled()
    item.set(True)
    agent = plistlib.loads((tmp_path / "Library/LaunchAgents" / f"{BUNDLE_ID}.plist").read_bytes())
    assert agent["Label"] == BUNDLE_ID and agent["RunAtLoad"]
    assert agent["ProgramArguments"] == ["/usr/bin/open", "/Applications/Marginalia.app"]
    assert item.enabled()
    item.set(False)
    assert not item.enabled()


def test_a_moved_mac_app_repoints_its_login_item(tmp_path):
    mac(tmp_path).set(True)
    moved = mac(tmp_path, exe="/Users/a/Applications/Marginalia.app/Contents/MacOS/Marginalia")
    moved.refresh()
    agent = plistlib.loads(moved.agent.read_bytes())
    assert agent["ProgramArguments"][1] == "/Users/a/Applications/Marginalia.app"


def test_refresh_leaves_it_off_when_off(tmp_path):
    item = mac(tmp_path)
    item.refresh()
    assert not item.enabled()


def test_windows_uses_the_run_key(tmp_path):
    run = FakeRun()
    item = LoginItem(platform="win32", frozen=True, executable=WIN_EXE, run_key=run)
    item.set(True)
    assert run.value == f'"{WIN_EXE}"' and item.enabled()
    run.value = '"D:\\old\\Marginalia.exe"'
    item.refresh()
    assert run.value == f'"{WIN_EXE}"', "an install that moved is pointed at again"
    item.set(False)
    assert run.value is None and not item.enabled()


@pytest.mark.parametrize(
    ("kw", "says"),
    [
        ({"platform": "linux", "frozen": True}, "Not available"),
        ({"platform": "darwin", "frozen": False}, "installed app"),
        ({"platform": "darwin", "frozen": True, "executable": "/Volumes/M/M.app/Contents/MacOS/M"}, "Applications"),
    ],
)
def test_only_an_installed_app_can_open_at_login(tmp_path, kw, says):
    item = LoginItem(executable=kw.pop("executable", MAC_EXE), home=tmp_path, **kw)
    assert says in item.problem
    with pytest.raises(OSError):
        item.set(True)


def test_a_copy_run_from_python_reports_off(tmp_path):
    mac(tmp_path).set(True)
    assert not mac(tmp_path, frozen=False).enabled()


@pytest.mark.skipif(sys.platform != "win32", reason="the real registry")
def test_the_real_run_key_round_trips():
    run = WindowsRun("Marginalia-test")
    try:
        run.set('"C:\\x.exe"')
        assert run.get() == '"C:\\x.exe"'
    finally:
        run.delete()
    assert run.get() is None
    run.delete()  # deleting what isn't there is fine
