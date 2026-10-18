"""1× RGB render of the overview grid (frames, borders, numbers, oversize thumbnails)."""

from collections.abc import Sequence

import numpy as np

from core.font8x8 import text_mask
from core.overview.layout import Geometry, compute_geometry, standard_size
from core.overview.options import CLASSIC_FONT, OverviewOptions
from core.palette import Palette

CROSS_PIXELS = ((1, 0), (0, 1), (1, 1), (2, 1), (1, 2))  # (x, y) of the 3×3 "+"


def thumbnail(frame: np.ndarray, std: tuple[int, int]) -> tuple[np.ndarray, bool]:
    """Fit an oversize frame into the standard size: keep the top, cut the bottom and left/right equally.

    Returns (pixels, was_oversize). The red cross is drawn by the renderer.
    """
    cw, ch = std
    h, w = frame.shape
    oversize = w > cw or h > ch
    if w > cw:
        x0 = (w - cw) // 2
        frame = frame[:, x0 : x0 + cw]
    if h > ch:
        frame = frame[:ch, :]
    return frame, oversize


def render_grid(
    frames: Sequence[np.ndarray],
    palette: Palette,
    opts: OverviewOptions,
    text_block_h: int | None = None,
) -> tuple[np.ndarray, Geometry]:
    """Numbers are drawn here only for the classic pixel font; other fonts are drawn after upscaling."""
    std = standard_size(frames)
    geo = compute_geometry(len(frames), std, opts, text_block_h)
    pixel_numbers = opts.number_font == CLASSIC_FONT
    canvas = np.zeros((geo.height, geo.width, 3), np.uint8)
    border = np.array(opts.border_rgb, np.uint8)
    number_color = np.array(opts.number_rgb, np.uint8)
    cross = np.array(opts.cross_rgb, np.uint8)
    pal = palette.rgb
    b = geo.border

    for i, frame in enumerate(frames):
        x0, y0 = geo.box_origin(i)
        if b:
            canvas[y0, x0 : x0 + geo.box_w] = border
            canvas[y0 + geo.box_h - 1, x0 : x0 + geo.box_w] = border
            canvas[y0 : y0 + geo.box_h, x0] = border
            canvas[y0 : y0 + geo.box_h, x0 + geo.box_w - 1] = border

        thumb, oversize = thumbnail(frame, std)
        fh, fw = thumb.shape
        ix, iy = x0 + b + (geo.cell_w - fw) // 2, y0 + b + (geo.cell_h - fh) // 2
        opaque = thumb > 0
        canvas[iy : iy + fh, ix : ix + fw][opaque] = pal[thumb[opaque]]
        if oversize:
            for dx, dy in CROSS_PIXELS:
                canvas[y0 + b + dy, x0 + b + dx] = cross

        if pixel_numbers and geo.text_h and i % opts.number_every == 0:
            mask = text_mask(str(i))
            tx = x0 + (geo.box_w - mask.shape[1]) // 2
            ty = geo.number_y(i)
            # clip to the canvas (long numbers in narrow cells)
            left, right = max(0, tx), min(geo.width, tx + mask.shape[1])
            if right > left:
                region = canvas[ty : ty + mask.shape[0], left:right]
                region[mask[:, left - tx : right - tx]] = number_color
    return canvas, geo
