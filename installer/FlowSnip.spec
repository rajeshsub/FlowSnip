# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for FlowSnip - all platforms.
# Run from the repo root:
#   pyinstaller installer/FlowSnip.spec
#
# Pre-requisite: run `python installer/pre_build.py` first to generate
# assets/icon.ico and assets/icon.icns from assets/icon.png.

import importlib.metadata
import platform
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # repo root
ASSETS = ROOT / "assets"

version = importlib.metadata.version("flowsnip")

# ffmpeg binary names per platform
_FFMPEG_BINS = {
    "Windows": ["ffmpeg.exe", "ffprobe.exe"],
    "Darwin": ["ffmpeg", "ffprobe"],
    "Linux": ["ffmpeg", "ffprobe"],
}
_os = platform.system()

datas = [
    (str(ASSETS / "icon.png"), "assets"),
    (str(ASSETS / "icon.ico"), "assets"),
    (str(ASSETS / "icon.icns"), "assets"),
    (str(ASSETS / "screenshot.png"), "assets"),
]

# Add ffmpeg binaries if present (downloaded by CI workflow)
for _bin in _FFMPEG_BINS.get(_os, []):
    _bin_path = ROOT / "ffmpeg_bin" / _bin
    if _bin_path.exists():
        datas.append((str(_bin_path), "."))

block_cipher = None

a = Analysis(
    [str(ROOT / "flowsnip" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "flowsnip",
        "flowsnip.config",
        "flowsnip.download_manager",
        "flowsnip.gui",
        "flowsnip.updater",
        "pydantic",
        "pydantic_settings",
        "customtkinter",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "yt_dlp",
        "packaging",
        "darkdetect",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FlowSnip",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / "icon.ico") if _os == "Windows" else str(ASSETS / "icon.icns"),
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FlowSnip",
)

if _os == "Darwin":
    app = BUNDLE(
        coll,
        name="FlowSnip.app",
        icon=str(ASSETS / "icon.icns"),
        bundle_identifier="com.rajeshsub.flowsnip",
        info_plist={
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "NSHighResolutionCapable": True,
        },
    )
