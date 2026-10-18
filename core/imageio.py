"""Lossless 8-bit indexed frame export (BMP, PCX, PNG, GIF, TIF) and frame file naming."""

import re
from pathlib import Path

import numpy as np
from PIL import Image

from core.palette import Palette

EXPORT_FORMATS: dict[str, str] = {"BMP": ".bmp", "PCX": ".pcx", "PNG": ".png", "GIF": ".gif", "TIF": ".tif"}
IMPORT_EXTENSIONS = (".bmp", ".pcx", ".png", ".gif", ".tif", ".tiff")
_FRAME_NAME = re.compile(r"^(\d+)\.(bmp|pcx|png|gif|tif|tiff)$", re.IGNORECASE)


def frame_to_image(pixels: np.ndarray, palette: Palette) -> Image.Image:
    im = Image.fromarray(np.ascontiguousarray(pixels, np.uint8), "P")
    im.putpalette(palette.flat())
    return im


def export_frame(pixels: np.ndarray, palette: Palette, path: Path) -> None:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in (*EXPORT_FORMATS.values(), ".tiff"):
        raise ValueError(f"Unsupported export format '{ext}'. Use BMP, PCX, PNG, GIF or TIF.")
    im = frame_to_image(pixels, palette)
    if ext in (".png", ".gif"):
        im.save(path, transparency=0)
    else:
        im.save(path)


def frame_filename(index: int, total: int, ext: str) -> str:
    digits = max(4, len(str(max(total - 1, 0))))
    return f"{index:0{digits}d}{ext}"


def parse_frame_filename(name: str) -> int | None:
    """'0018.tif' -> 18; anything else -> None."""
    m = _FRAME_NAME.match(name)
    return int(m.group(1)) if m else None
