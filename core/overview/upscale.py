"""Upscalers for the final overview.

"photoshop": a learned 7×7 linear filter per output sub-pixel, fitted (least squares) to the
Photoshop "Preserve Details 2.0" ×2 result `MaxiMap_x2rgb.png` from its exact 1× input.
Hold-out PSNR vs. Photoshop: 35.2 dB (nearest 29.9, Lanczos 28.4).
"""

from functools import cache

import numpy as np
from PIL import Image

from core.paths import PS2X_KERNEL_PATH

METHODS: dict[str, str] = {
    "photoshop": "Photoshop-like (calibrated)",
    "nearest": "Nearest neighbour (exact pixels)",
    "scale2x": "Scale2x (pixel art)",
    "lanczos": "Lanczos (soft)",
}
_R = 3
_OFFSETS = [(dy, dx) for dy in range(-_R, _R + 1) for dx in range(-_R, _R + 1)]


@cache
def _kernel() -> np.ndarray:
    k = np.load(PS2X_KERNEL_PATH).astype(np.float32)  # (2, 2, 49 weights + bias)
    if k.shape != (2, 2, len(_OFFSETS) + 1):
        raise ValueError(f"Unexpected kernel shape {k.shape}")
    return k


def _photoshop2x(rgb: np.ndarray) -> np.ndarray:
    h, w, _ = rgb.shape
    pad = np.pad(rgb.astype(np.float32), ((_R, _R), (_R, _R), (0, 0)), mode="edge")
    k = _kernel()
    out = np.empty((2 * h, 2 * w, 3), np.uint8)
    tmp = np.empty((h, w, 3), np.float32)
    for py in (0, 1):
        for px in (0, 1):
            weights = k[py, px]
            acc = np.full((h, w, 3), weights[-1], np.float32)
            for j, (dy, dx) in enumerate(_OFFSETS):
                np.multiply(pad[_R + dy : _R + dy + h, _R + dx : _R + dx + w], weights[j], out=tmp)
                acc += tmp
            np.rint(acc, out=acc)
            np.clip(acc, 0, 255, out=acc)
            out[py::2, px::2] = acc.astype(np.uint8)
    return out


def _scale2x(a: np.ndarray) -> np.ndarray:
    """EPX / Scale2x: pixel-art upscaling that only uses existing colours."""
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode="edge")
    up, left, right, down = p[:-2, 1:-1], p[1:-1, :-2], p[1:-1, 2:], p[2:, 1:-1]

    def eq(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return np.all(x == y, axis=-1)

    cond = ~eq(up, down) & ~eq(left, right)
    out = np.empty((a.shape[0] * 2, a.shape[1] * 2, 3), a.dtype)
    out[0::2, 0::2] = np.where((cond & eq(left, up))[..., None], left, a)
    out[0::2, 1::2] = np.where((cond & eq(up, right))[..., None], right, a)
    out[1::2, 0::2] = np.where((cond & eq(left, down))[..., None], left, a)
    out[1::2, 1::2] = np.where((cond & eq(down, right))[..., None], right, a)
    return out


def upscale(rgb: np.ndarray, factor: int, method: str) -> np.ndarray:
    if factor not in (1, 2, 4):
        raise ValueError("Scale must be 1, 2 or 4.")
    if factor == 1:
        return rgb
    if method == "nearest":
        return np.repeat(np.repeat(rgb, factor, 0), factor, 1)
    if method == "lanczos":
        h, w, _ = rgb.shape
        return np.asarray(Image.fromarray(rgb).resize((w * factor, h * factor), Image.LANCZOS))
    step = {"photoshop": _photoshop2x, "scale2x": _scale2x}.get(method)
    if step is None:
        raise ValueError(f"Unknown upscale method '{method}'.")
    out = rgb
    for _ in range(factor.bit_length() - 1):
        out = step(out)
    return out
