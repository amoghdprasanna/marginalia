"""Build the desktop app, and on macOS sign, notarise and wrap it in a disk image.

    pip install -e ".[package]"          # plus ".[ocr,voice,openai,gemini]" to bundle those features
    python packaging/build.py            # -> dist/Marginalia.app and dist/Marginalia-<v>-macos.dmg
                                         #    (Windows: dist/Marginalia-<v>-windows-setup.exe,
                                         #     Linux: dist/marginalia_<v>_amd64.deb)

On Windows the installer is compiled with Inno Setup 6 (ISCC on PATH, in its usual folder, or
named by the ISCC environment variable). Without it you get a .zip of the app instead, which
runs but can't update itself.

Signing and notarisation happen only when these are set (CI reads them from secrets):
    MACOS_SIGN_IDENTITY   "Developer ID Application: Your Name (TEAMID)"
    APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD   for notarytool (an app-specific password)
Without them you get an unsigned app: fine on your own Mac, blocked by Gatekeeper elsewhere.
"""
from __future__ import annotations

import json
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


# What the bundled Qt and PortAudio load from the system rather than carry (ADR 0033): Qt's xcb
# platform plugin and its GL, font and D-Bus needs, and PortAudio for asking by voice.
DEB_DEPENDS = (
    "libegl1, libgl1, libglib2.0-0, libfontconfig1, libdbus-1-3, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0,"
    " libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0,"
    " libxcb-xinerama0, libxcb-xkb1, libportaudio2"
)
DEB_MAINTAINER = "Marginalia <amoghdprasanna@users.noreply.github.com>"


def deb_control(version: str, arch: str, installed_kb: int) -> str:
    return (
        f"Package: marginalia\nVersion: {version}\nArchitecture: {arch}\nMaintainer: {DEB_MAINTAINER}\n"
        f"Installed-Size: {installed_kb}\nDepends: {DEB_DEPENDS}\nSection: education\nPriority: optional\n"
        "Homepage: https://github.com/amoghdprasanna/marginalia\n"
        "Description: Screen-aware study companion\n"
        " Ask about whatever you're reading or watching; Marginalia answers in a small bubble and\n"
        " points at the parts of the screen it's talking about.\n"
    )


DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=Marginalia
Comment=Ask about what's on your screen
Exec=/opt/marginalia/Marginalia
Icon=marginalia
Terminal=false
Categories=Education;Utility;
StartupWMClass=Marginalia
"""


def linux() -> Path:
    """A .deb that installs from the Software app with a double-click: the app in /opt, a menu
    entry, the icon, and the notebook extension's helper registered for every user."""
    from marginalia.browser.install import HOST_NAME, LINUX_SYSTEM_DIRS, manifest

    arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, check=True).stdout.strip()
    root = DIST / "deb"
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(DIST / "Marginalia", root / "opt" / "marginalia", symlinks=True)
    (root / "usr" / "bin").mkdir(parents=True)
    (root / "usr" / "bin" / "marginalia").symlink_to("/opt/marginalia/Marginalia")
    apps = root / "usr" / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "marginalia.desktop").write_text(DESKTOP_ENTRY, encoding="utf-8")
    for size in (16, 32, 64, 128, 256, 512):
        png = ROOT / "packaging" / "build" / f"icon_{size}.png"
        if png.exists():
            folder = root / "usr" / "share" / "icons" / "hicolor" / f"{size}x{size}" / "apps"
            folder.mkdir(parents=True)
            shutil.copy(png, folder / "marginalia.png")
    text = json.dumps(manifest(Path("/opt/marginalia/Marginalia")), indent=2) + "\n"
    for folder in LINUX_SYSTEM_DIRS:
        target = root / folder.lstrip("/")
        target.mkdir(parents=True)
        (target / f"{HOST_NAME}.json").write_text(text, encoding="utf-8")
    size_kb = sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and not f.is_symlink()) // 1024
    (root / "DEBIAN").mkdir()
    (root / "DEBIAN" / "control").write_text(deb_control(__version__, arch, size_kb), encoding="utf-8")
    for path in root.rglob("*"):  # dpkg wants plain permissions: nothing group- or world-writable
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() or os.access(path, os.X_OK) else 0o644)
    deb = DIST / f"marginalia_{__version__}_{arch}.deb"
    deb.unlink(missing_ok=True)
    run("dpkg-deb", "--build", "--root-owner-group", "-Zxz", str(root), str(deb))
    shutil.rmtree(root)
    return deb


def main() -> None:
    pyinstaller()
    if sys.platform == "darwin":
        result = macos()
    elif sys.platform == "win32":
        result = windows()
    elif shutil.which("dpkg-deb"):
        result = linux()
    else:
        print("dpkg-deb not found: leaving the app folder unpackaged.")
        result = DIST / "Marginalia"
    print(f"Built {result}")


if __name__ == "__main__":
    main()
