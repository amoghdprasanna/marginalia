# PyInstaller spec for the desktop app. Run through packaging/build.py, which makes the icon
# first and signs, notarises and wraps the result (ADR 0023).
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821  (SPECPATH is defined by PyInstaller)
sys.path.insert(0, str(ROOT / "src"))
from marginalia import __version__  # noqa: E402

BUILD = ROOT / "packaging" / "build"
ICON = BUILD / ("icon.icns" if sys.platform == "darwin" else "icon.ico")
SIGN_IDENTITY = os.environ.get("MACOS_SIGN_IDENTITY") or None
ENTITLEMENTS = str(ROOT / "packaging" / "macos" / "entitlements.plist")

# keyring and pynput pick their platform backend at runtime by name, which static analysis misses.
hiddenimports = collect_submodules("keyring.backends") + ["keyring.backends.macOS", "keyring.backends.Windows"]
if sys.platform == "win32":
    hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32"]
elif sys.platform.startswith("linux"):
    hiddenimports += ["pynput.keyboard._xorg", "pynput.mouse._xorg"]

# The optional extras ship model files as package data; bundle them only when installed.
datas = []
for pkg in ("rapidocr_onnxruntime", "faster_whisper"):
    try:
        datas += collect_data_files(pkg)
    except Exception:  # noqa: BLE001
        pass

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "PySide6.Qt3DCore", "PySide6.QtWebEngineCore", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Marginalia",
    console=False,
    icon=str(ICON) if ICON.exists() else None,
    codesign_identity=SIGN_IDENTITY,
    entitlements_file=ENTITLEMENTS if SIGN_IDENTITY else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Marginalia")  # noqa: F821

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="Marginalia.app",
        icon=str(ICON) if ICON.exists() else None,
        bundle_identifier="io.github.amoghdprasanna.marginalia",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": "Marginalia",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            # An overlay, not a document app: no Dock icon; the orb and its menu are the UI.
            "LSUIElement": True,
            "NSMicrophoneUsageDescription": (
                "Marginalia listens only while you ask a question by voice. Speech is transcribed on this Mac."
            ),
        },
    )
