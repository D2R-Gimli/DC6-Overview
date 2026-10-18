"""Grid geometry (1× native pixels), standard frame size and oversize detection."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from core.font8x8 import GLYPH_H
from core.overview.options import OverviewOptions

TEXT_BLOCK_H = GLYPH_H + 1  # v1.0: NUMBER_HEIGHT 8 + NUMBER_TO_BORDER 1


def standard_size(frames: Sequence[np.ndarray]) -> tuple[int, int]:
    """Most common (w, h). Ties: the size seen first."""
    if not frames:
        raise ValueError("No frames.")
    return Counter((f.shape[1], f.shape[0]) for f in frames).most_common(1)[0][0]


def oversize_frames(frames: Sequence[np.ndarray], std: tuple[int, int]) -> list[int]:
    cw, ch = std
    return [i for i, f in enumerate(frames) if f.shape[1] > cw or f.shape[0] > ch]


@dataclass(slots=True, frozen=True)
class Geometry:
    cell_w: int  # frame area
    cell_h: int
    border: int
    box_w: int  # frame area + borders
    box_h: int
    text_h: int
    pitch_x: int
    pitch_y: int
    margin: int
    cols: int
    rows: int
    width: int
    height: int

    def box_origin(self, index: int) -> tuple[int, int]:
        """Top-left of the bordered box of frame `index`."""
        col, row = index % self.cols, index // self.cols
        return self.margin + col * self.pitch_x, row * self.pitch_y + self.text_h

    def number_y(self, index: int) -> int:
        return (index // self.cols) * self.pitch_y


def compute_geometry(
    count: int, std: tuple[int, int], opts: OverviewOptions, text_block_h: int | None = None
) -> Geometry:
    """`text_block_h`: height of the number row (default: classic 8×8 font + 1 px)."""
    if count <= 0:
        raise ValueError("No frames.")
    cw, ch = std
    b = 1 if opts.show_border else 0
    text_h = (text_block_h or TEXT_BLOCK_H) if opts.number_every > 0 else 0
    cols = max(1, min(opts.columns, count))
    rows = -(-count // cols)
    box_w, box_h = cw + 2 * b, ch + 2 * b
    margin = max(0, opts.side_margin)

    if b and opts.collapse_borders and opts.spacing_x == 0:
        pitch_x = cw + 1
    else:
        pitch_x = box_w + max(0, opts.spacing_x)
    width = 2 * margin + (cols - 1) * pitch_x + box_w

    if b and opts.collapse_borders and opts.spacing_y == 0 and text_h == 0:
        pitch_y = ch + 1
        height = (rows - 1) * pitch_y + box_h
    else:
        pitch_y = text_h + box_h + max(0, opts.spacing_y)
        height = rows * pitch_y  # v1.0 keeps the spacing below the last row as well
    return Geometry(cw, ch, b, box_w, box_h, text_h, pitch_x, pitch_y, margin, cols, rows, width, height)
