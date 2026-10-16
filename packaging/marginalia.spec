# PyInstaller spec for the desktop app. Run through packaging/build.py, which makes the icon
# first and signs, notarises and wraps the result (ADR 0023).
import os
import re
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
# macOS reads text with its own Vision framework (ADR 0026), so RapidOCR and the OpenCV it pulls in
# (about 140 MB) stay out even if they happen to be installed in the build environment.
RAPIDOCR_STACK = ["rapidocr_onnxruntime", "rapidocr", "cv2", "shapely", "pyclipper"]
datas = collect_data_files("marginalia")  # the UI's icons
for pkg in ("faster_whisper",) + (() if sys.platform == "darwin" else ("rapidocr_onnxruntime",)):
    try:
        datas += collect_data_files(pkg)
    except Exception:  # noqa: BLE001
        pass

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "tkinter", "pytest", "PySide6.Qt3DCore", "PySide6.QtWebEngineCore", "PySide6.QtQuick",
        "hf_xet",  # huggingface_hub's faster download path; without it, it downloads over plain HTTPS
    ] + (RAPIDOCR_STACK if sys.platform == "darwin" else []),
    noarchive=False,
)

# Qt pieces that plugins drag in and nothing here uses: the virtual-keyboard input plugin brings
# QtQuick and QtQml, the PDF image-format plugin brings QtPdf, and Qt's translations are for its
# stock dialogs, which we don't show. About 25 MB. (The SVG plugins stay: the UI draws an SVG.)
UNUSED_QT = re.compile(
    r"PySide6/(.+/)?(Qt6?(Quick|Qml|VirtualKeyboard|Pdf)|platforminputcontexts/|imageformats/(lib)?qpdf|translations/)"
)


def used(entry):  # (name in the bundle, source path or, for a SYMLINK, its target, typecode)
    return not UNUSED_QT.search(f"{entry[0]} {entry[1]}".replace("\\", "/"))


a.binaries = [entry for entry in a.binaries if used(entry)]
a.datas = [entry for entry in a.datas if used(entry)]
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
