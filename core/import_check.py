"""Check an image before it replaces a DC6 frame. Every problem says what is wrong and how to fix it."""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from core.dc6 import GAME_MAX_SIZE
from core.palette import Palette
from core.rle import decode_frame, encode_frame

FIX_INDEXED = (
    "Convert it to Indexed colour (8-bit) with the {pal} palette, without dithering, and save again."
)


@dataclass(slots=True)
class ImportCheck:
    path: Path
    indices: np.ndarray | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    size_differs: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors and self.indices is not None

    @property
    def size(self) -> tuple[int, int] | None:
        return None if self.indices is None else (self.indices.shape[1], self.indices.shape[0])


def check_image(
    path: Path, palette: Palette, target_size: tuple[int, int] | None = None, frame_index: int | None = None
) -> ImportCheck:
    """`target_size` = (w, h) of the frame being replaced, or None (e.g. a blank frame)."""
    path = Path(path)
    res = ImportCheck(path)
    pal_name = palette.name or "act1"
    try:
        im = Image.open(path)
        im.load()
    except (OSError, UnidentifiedImageError, ValueError) as e:
        res.errors.append(f"Cannot read the file ({e}). Save it as an 8-bit BMP, PCX, PNG, GIF or TIF.")
        return res

    frames_in_file = getattr(im, "n_frames", 1)
    if frames_in_file > 1:
        res.warnings.append(f"The file contains {frames_in_file} images; only the first one is used.")
    w, h = im.size
    if w == 0 or h == 0:
        res.errors.append("The image is empty (0 pixels wide or high).")
        return res

    indices = _to_indices(im, palette, pal_name, res)
    if indices is None:
        return res

    if target_size is not None and (w, h) != target_size:
        tw, th = target_size
        res.size_differs = True
        what = "bigger" if w >= tw and h >= th else "smaller" if w <= tw and h <= th else "a different size"
        frame = f"frame {frame_index:04d}" if frame_index is not None else "the frame"
        res.warnings.append(
            f"The image is {w}×{h}, but {frame} is {tw}×{th} ({what} than the existing frame)."
        )
    if w > GAME_MAX_SIZE or h > GAME_MAX_SIZE:
        res.warnings.append(f"{w}×{h} is larger than 256×256: Diablo II can't display frames this big.")

    decoded, problems = decode_frame(encode_frame(indices), w, h)
    if problems or not np.array_equal(decoded, indices):
        res.errors.append(
            "Internal round-trip check failed (encode → decode differs). Please report this file."
        )
        return res
    res.indices = indices
    return res


def _to_indices(im: Image.Image, palette: Palette, pal_name: str, res: ImportCheck) -> np.ndarray | None:
    if im.mode == "P":
        idx = np.asarray(im, np.uint8)
        img_pal = np.array((im.getpalette() or [])[:768], np.uint8)
        img_pal = np.pad(img_pal, (0, 768 - len(img_pal))).reshape(256, 3)
        mask = _transparent_mask_p(im, idx, res)
        if mask is None:
            return None
        used = np.unique(idx[~mask])
        if np.array_equal(img_pal[used], palette.rgb[used]):
            res.notes.append(f"Indexed image with the {pal_name} palette: taken 1:1.")
            out = idx.copy()
            out[mask] = 0
            return out
        res.notes.append(f"Indexed image with a different palette: colours mapped exactly to {pal_name}.")
        return _map_rgb(img_pal[idx], mask, palette, pal_name, res)

    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        rgba = np.asarray(im.convert("RGBA"), np.uint8)
        alpha = rgba[..., 3]
        semi = (alpha > 0) & (alpha < 255)
        if semi.any():
            y, x = np.argwhere(semi)[0]
            res.errors.append(
                f"{int(semi.sum())} semi-transparent pixel(s) (first at x={x}, y={y}). "
                "Use only fully transparent or fully opaque pixels."
            )
            return None
        res.notes.append(f"{im.mode} image: colours mapped exactly to {pal_name}.")
        return _map_rgb(rgba[..., :3], alpha == 0, palette, pal_name, res)

    rgb = np.asarray(im.convert("RGB"), np.uint8)
    res.notes.append(f"{im.mode} image: colours mapped exactly to {pal_name}.")
    return _map_rgb(rgb, np.zeros(rgb.shape[:2], bool), palette, pal_name, res)


def _transparent_mask_p(im: Image.Image, idx: np.ndarray, res: ImportCheck) -> np.ndarray | None:
    trans = im.info.get("transparency")
    if trans is None:
        return np.zeros(idx.shape, bool)
    if isinstance(trans, int):
        return idx == trans
    alpha = np.frombuffer(bytes(trans), np.uint8)
    alpha = np.pad(alpha, (0, 256 - len(alpha)), constant_values=255)
    a = alpha[idx]
    semi = (a > 0) & (a < 255)
    if semi.any():
        y, x = np.argwhere(semi)[0]
        res.errors.append(
            f"{int(semi.sum())} semi-transparent pixel(s) (first at x={x}, y={y}). "
            "Use only fully transparent or fully opaque pixels."
        )
        return None
    return a == 0


def _map_rgb(
    rgb: np.ndarray, transparent: np.ndarray, palette: Palette, pal_name: str, res: ImportCheck
) -> np.ndarray | None:
    """Exact colour match only. Pure black and transparent pixels become index 0 (D2 transparency)."""
    key = (rgb[..., 0].astype(np.uint32) << 16) | (rgb[..., 1].astype(np.uint32) << 8) | rgb[..., 2]
    lookup: dict[int, int] = {}
    pal_keys = (
        (palette.rgb[:, 0].astype(np.uint32) << 16)
        | (palette.rgb[:, 1].astype(np.uint32) << 8)
        | palette.rgb[:, 2]
    )
    for i in range(255, 0, -1):  # lowest index wins
        lookup[int(pal_keys[i])] = i
    lookup[0] = 0
    uniq, inverse = np.unique(key, return_inverse=True)
    mapped = np.array([lookup.get(int(k), -1) for k in uniq], np.int32)[inverse].reshape(key.shape)
    bad = (mapped < 0) & ~transparent
    if bad.any():
        y, x = np.argwhere(bad)[0]
        r, g, b = (int(v) for v in rgb[y, x])
        n_colours = len(np.unique(key[bad]))
        res.errors.append(
            f"{n_colours} colour(s) in {int(bad.sum())} pixel(s) are not in the {pal_name} palette "
            f"(first at x={x}, y={y}: RGB {r},{g},{b}). " + FIX_INDEXED.format(pal=pal_name)
        )
        return None
    mapped[transparent] = 0
    return mapped.astype(np.uint8)
