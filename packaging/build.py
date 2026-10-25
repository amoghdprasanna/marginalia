"""Build the desktop app, and on macOS sign, notarise and wrap it in a disk image.

    pip install -e ".[package]"          # plus ".[ocr,voice,openai,gemini]" to bundle those features
    python packaging/build.py            # -> dist/Marginalia.app and dist/Marginalia-<v>-macos.dmg
                                         #    (Windows: dist/Marginalia-<v>-windows-setup.exe)

On Windows the installer is compiled with Inno Setup 6 (ISCC on PATH, in its usual folder, or
named by the ISCC environment variable). Without it you get a .zip of the app instead, which
runs but can't update itself.

Signing and notarisation happen only when these are set (CI reads them from secrets):
    MACOS_SIGN_IDENTITY   "Developer ID Application: Your Name (TEAMID)"
    APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD   for notarytool (an app-specific password)
Without them you get an unsigned app: fine on your own Mac, blocked by Gatekeeper elsewhere.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "src"))
from marginalia import __version__  # noqa: E402


def run(*cmd: str) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def pyinstaller() -> None:
    run(sys.executable, str(ROOT / "packaging" / "make_icon.py"))
    run(
        sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / "marginalia.spec"),
        "--noconfirm", "--clean", "--distpath", str(DIST), "--workpath", str(ROOT / "packaging" / "build" / "work"),
    )  # fmt: skip


def notarise(path: Path) -> None:
    """Submit to Apple's notary service and staple the ticket, so it opens offline too."""
    creds = [os.environ.get(k) for k in ("APPLE_ID", "APPLE_TEAM_ID", "APPLE_APP_PASSWORD")]
    if not all(creds):
        print(f"Not notarising {path.name}: APPLE_ID, APPLE_TEAM_ID and APPLE_APP_PASSWORD are not all set.")
        return
    apple_id, team, password = creds
    upload = path
    if path.suffix == ".app":  # notarytool takes a zip, dmg or pkg
        upload = path.with_suffix(".zip")
        run("ditto", "-c", "-k", "--keepParent", str(path), str(upload))
    run(
        "xcrun", "notarytool", "submit", str(upload), "--apple-id", apple_id, "--team-id", team,
        "--password", password, "--wait",
    )  # fmt: skip
    run("xcrun", "stapler", "staple", str(path))
    if upload != path:
        upload.unlink()


def macos() -> Path:
    app = DIST / "Marginalia.app"
    # PyInstaller leaves the one-folder build next to the bundle it copied it into; only the .app ships.
    shutil.rmtree(DIST / "Marginalia", ignore_errors=True)
    identity = os.environ.get("MACOS_SIGN_IDENTITY")
    if identity:
        # PyInstaller signed each binary; sign the bundle as a whole with the hardened runtime.
        run(
            "codesign", "--force", "--options", "runtime", "--timestamp", "--entitlements",
            str(ROOT / "packaging" / "macos" / "entitlements.plist"), "--sign", identity, str(app),
        )  # fmt: skip
        run("codesign", "--verify", "--strict", "--verbose=2", str(app))
        notarise(app)
    else:
        print("Not signing: MACOS_SIGN_IDENTITY is not set. The app runs here but Gatekeeper will block it elsewhere.")

    stage = DIST / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    run("ditto", str(app), str(stage / "Marginalia.app"))
    (stage / "Applications").symlink_to("/Applications")
    dmg = DIST / f"Marginalia-{__version__}-macos.dmg"
    dmg.unlink(missing_ok=True)
    run("hdiutil", "create", "-volname", "Marginalia", "-srcfolder", str(stage), "-ov", "-format", "UDZO", str(dmg))
    shutil.rmtree(stage)
    if identity:
        run("codesign", "--force", "--timestamp", "--sign", identity, str(dmg))
        notarise(dmg)
    return dmg


def find_iscc() -> str | None:
    """Inno Setup's compiler: named by ISCC, on PATH, or where its installer puts it."""
    env = os.environ.get
    local = env("LOCALAPPDATA")
    folders = [env("ProgramFiles(x86)"), env("ProgramFiles"), local and Path(local) / "Programs"]
    candidates = [env("ISCC"), shutil.which("iscc")] + [Path(f) / "Inno Setup 6" / "ISCC.exe" for f in folders if f]
    found = next((c for c in candidates if c and Path(c).exists()), None)
    return str(found) if found else None


def windows() -> Path:
    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup not found: making a .zip instead of an installer (it can't update itself).")
        out = DIST / f"Marginalia-{__version__}-windows"
        shutil.make_archive(str(out), "zip", DIST, "Marginalia")
        return out.with_suffix(".zip")
    icon = ROOT / "packaging" / "build" / "icon.ico"
    run(
        iscc, f"/DAppVersion={__version__}", f"/DSourceDir={DIST / 'Marginalia'}", f"/DOutputDir={DIST}",
        *([f"/DIconFile={icon}"] if icon.exists() else []), str(ROOT / "packaging" / "windows" / "marginalia.iss"),
    )  # fmt: skip
    return DIST / f"Marginalia-{__version__}-windows-setup.exe"


def main() -> None:
    pyinstaller()
    if sys.platform == "darwin":
        result = macos()
    elif sys.platform == "win32":
        result = windows()
    else:
        result = DIST / "Marginalia"
    print(f"Built {result}")


if __name__ == "__main__":
    main()
