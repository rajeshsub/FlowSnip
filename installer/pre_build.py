"""
Pre-build script: converts assets/icon.png to platform icon formats.

Run before PyInstaller:
    python installer/pre_build.py

Produces:
    assets/icon.ico   - Windows (16/32/48/256 px multi-resolution)
    assets/icon.icns  - macOS
"""

import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).parent.parent
SRC = REPO_ROOT / "assets" / "icon.png"
ICO = REPO_ROOT / "assets" / "icon.ico"
ICNS = REPO_ROOT / "assets" / "icon.icns"


def make_ico() -> None:
    img = Image.open(SRC).convert("RGBA")
    sizes = [(16, 16), (32, 32), (48, 48), (256, 256)]
    imgs = [img.resize(s, Image.LANCZOS) for s in sizes]
    imgs[0].save(ICO, format="ICO", sizes=sizes, append_images=imgs[1:])
    print(f"  wrote {ICO}")


def make_icns() -> None:
    img = Image.open(SRC).convert("RGBA")
    img.save(ICNS, format="ICNS")
    print(f"  wrote {ICNS}")


if __name__ == "__main__":
    print("Converting icon.png …")
    make_ico()
    make_icns()
    print("Done.")
    sys.exit(0)
