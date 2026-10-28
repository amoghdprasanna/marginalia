"""The helper's manifest for Chrome and its relatives."""
import json
from pathlib import Path

from marginalia.browser.install import (
    EXTENSION_ID,
    HOST_NAME,
    browser_dirs,
    check,
    install,
    manifest,
    uninstall,
)


def test_manifest_allows_only_our_extension():
    m = manifest(Path("/x/marginalia-browser-host"))
    assert m["name"] == HOST_NAME and m["type"] == "stdio"
    assert m["allowed_origins"] == [f"chrome-extension://{EXTENSION_ID}/"]


def test_only_browsers_that_are_installed(tmp_path):
    support = tmp_path / "Library" / "Application Support"
    (support / "Google" / "Chrome").mkdir(parents=True)
    assert browser_dirs(tmp_path, "darwin") == [support / "Google" / "Chrome" / "NativeMessagingHosts"]
    assert browser_dirs(tmp_path, "sunos") == []


def test_linux_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    (tmp_path / "cfg" / "chromium").mkdir(parents=True)
    assert browser_dirs(tmp_path, "linux") == [tmp_path / "cfg" / "chromium" / "NativeMessagingHosts"]


def test_install_then_uninstall(tmp_path):
    dirs = [tmp_path / "a" / "NativeMessagingHosts", tmp_path / "b" / "NativeMessagingHosts"]
    written = install(dirs, Path("/opt/helper"))
    assert [p.name for p in written] == [f"{HOST_NAME}.json"] * 2
    assert json.loads(written[0].read_text())["path"] == str(Path("/opt/helper"))
    assert uninstall(dirs) == written
    assert not any(p.exists() for p in written)


def test_check_says_what_is_wrong(tmp_path):
    folder = tmp_path / "NativeMessagingHosts"
    ok, lines = check([folder])
    assert not ok and "install" in lines[0]

    program = tmp_path / "helper"
    program.write_text("#!/bin/sh\n")
    program.chmod(0o755)
    install([folder], program)
    ok, lines = check([folder], hello=lambda: {"modelName": "Claude Haiku 5.5", "hasKey": True})
    assert ok, lines
    assert "Claude key: found" in lines[-1]

    stale = manifest(program, extension_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    (folder / f"{HOST_NAME}.json").write_text(json.dumps(stale))
    ok, lines = check([folder], hello=lambda: {"hasKey": False})
    assert not ok
    assert any("not chrome-extension://" in line for line in lines)
    assert "missing: add it" in lines[-1]


def test_check_reports_a_helper_that_cannot_start(tmp_path):
    folder = tmp_path / "NativeMessagingHosts"
    program = tmp_path / "helper"
    program.write_text("")
    program.chmod(0o755)
    install([folder], program)

    def broken():
        raise RuntimeError("keyring locked")

    ok, lines = check([folder], hello=broken)
    assert not ok and "keyring locked" in lines[-1]
