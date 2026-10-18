"""Locations of bundled files. Works from source and from a PyInstaller/Nuitka bundle."""

import sys
from pathlib import Path

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    APP_DIR = Path(sys._MEIPASS)  # PyInstaller one-file: files are unpacked here
else:
    APP_DIR = Path(__file__).resolve().parents[1]  # the folder that contains main.py

ASSETS_DIR = APP_DIR / "gui" / "assets"
PALETTES_DIR = ASSETS_DIR / "palettes"
LOGO_PATH = ASSETS_DIR / "gimli.png"
ICON_PATH = ASSETS_DIR / "icon.ico"
PS2X_KERNEL_PATH = APP_DIR / "core" / "overview" / "data" / "ps2x_kernel.npy"
