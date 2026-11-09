"""Building the Mac app: how it is signed decides whether macOS remembers its permissions."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from marginalia import BUNDLE_ID

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def build(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("build", ROOT / "packaging" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.commands = []
    monkeypatch.setattr(module, "DIST", tmp_path)
    monkeypatch.setattr(module, "run", lambda *cmd: module.commands.append(list(cmd)))
    monkeypatch.setattr(module, "notarise", lambda path: module.commands.append(["notarise", path.name]))
    return module


def codesigns(build):
    return [c for c in build.commands if c[0] == "codesign"]


def test_an_unsigned_build_names_the_app_as_its_requirement(build, monkeypatch):
    """Bug: each ad-hoc build's requirement was its own hash, so after an update macOS no longer
    applied the Screen Recording grant and kept asking for it."""
    monkeypatch.delenv("MACOS_SIGN_IDENTITY", raising=False)
    build.macos()
    app = str(build.DIST / "Marginalia.app")
    assert codesigns(build) == [
        ["codesign", "--force", "--sign", "-", f'-r=designated => identifier "{BUNDLE_ID}"', app]
    ]
    assert not any(c[0] == "notarise" for c in build.commands), "nothing to notarise without a Developer ID"


def test_a_developer_id_build_is_signed_with_it_not_ad_hoc(build, monkeypatch):
    monkeypatch.setenv("MACOS_SIGN_IDENTITY", "Developer ID Application: Someone (TEAM123)")
    build.macos()
    signs = codesigns(build)
    assert signs and all(c[c.index("--sign") + 1] != "-" for c in signs if "--sign" in c)
    assert not any(a.startswith("-r=") for c in signs for a in c), "a Developer ID's own requirement is stable"
    assert ["notarise", "Marginalia.app"] in build.commands


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("codesign"), reason="needs macOS codesign")
def test_codesign_accepts_the_requirement_and_records_it(build, tmp_path):
    """The real codesign, on a tiny bundle: the requirement must parse and be what macOS reads back."""
    app = tmp_path / "Tiny.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    shutil.copy("/usr/bin/true", app / "Contents" / "MacOS" / "Tiny")
    (app / "Contents" / "Info.plist").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>'
        f"<key>CFBundleIdentifier</key><string>{BUNDLE_ID}</string>"
        "<key>CFBundleExecutable</key><string>Tiny</string></dict></plist>"
    )
    subprocess.run(build.adhoc_sign(app), check=True, capture_output=True)
    shown = subprocess.run(["codesign", "-d", "-r-", str(app)], capture_output=True, text=True, check=True)
    assert f'designated => identifier "{BUNDLE_ID}"' in shown.stdout + shown.stderr
    subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True)
