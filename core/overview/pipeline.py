"""DC6 frames → final overview image (render 1×, upscale, add header) and PNG + JPG export."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from math import ceil
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter

from core.overview.header import HeaderInfo, compose
from core.overview.layout import Geometry, oversize_frames, standard_size
from core.overview.options import CLASSIC_FONT, OverviewOptions
from core.overview.render import render_grid
from core.overview.upscale import upscale
from core.palette import Palette

HEADER_H_1X = 50  # header height per scale unit (×2 → 100 px, like the example)
DIGITS = "0123456789"


@dataclass(slots=True)
class OverviewResult:
    image: QImage
    geometry: Geometry
    oversize: list[int]
    frame_count: int


def rgb_to_qimage(rgb: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(rgb)
    h, w, _ = rgb.shape
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def number_font(opts: OverviewOptions, scale: int) -> QFont:
    font = QFont(opts.number_font)
    font.setPixelSize(max(1, opts.number_size * scale))
    font.setBold(opts.number_bold)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return font


def number_block_height(opts: OverviewOptions) -> int:
    """Height (×1 pixels) of the row above each line of boxes: digit height + 1 px gap + 1 px top."""
    digits_h = QFontMetricsF(number_font(opts, 1)).tightBoundingRect(DIGITS).height()
    return max(3, ceil(digits_h) + 2)


def draw_numbers(body: QImage, geo: Geometry, opts: OverviewOptions, count: int) -> QImage:
    """Frame numbers in a Windows font, drawn sharp at the final resolution."""
    s = opts.scale
    img = body.convertToFormat(QImage.Format.Format_RGB32)
    font = number_font(opts, s)
    fm = QFontMetricsF(font)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setFont(font)
    p.setPen(QColor(*opts.number_rgb))
    for i in range(0, count, opts.number_every):
        x0, y0 = geo.box_origin(i)
        text = str(i)
        width = fm.horizontalAdvance(text)
        baseline = (y0 - 1) * s - fm.tightBoundingRect(DIGITS).bottom()
        p.drawText(QPointF((x0 + geo.box_w / 2) * s - width / 2, baseline), text)
    p.end()
    return img


def build_overview(
    frames: Sequence[np.ndarray],
    palette: Palette,
    opts: OverviewOptions,
    file_name: str,
    created: str | None = None,
) -> OverviewResult:
    vector_numbers = opts.number_every > 0 and opts.number_font != CLASSIC_FONT
    block_h = number_block_height(opts) if vector_numbers else None
    grid, geo = render_grid(frames, palette, opts, block_h)
    big = rgb_to_qimage(upscale(grid, opts.scale, opts.upscale_method))
    if vector_numbers:
        big = draw_numbers(big, geo, opts, len(frames))
    oversize = oversize_frames(frames, standard_size(frames))
    info = HeaderInfo(
        file_name,
        len(frames),
        oversize,
        created or date.today().strftime("%d.%m.%Y"),
        opts.text_line1,
        opts.text_line2,
    )
    image = compose(big, info, HEADER_H_1X * opts.scale, opts.header_gap)
    return OverviewResult(image, geo, oversize, len(frames))


def output_paths(out_dir: Path, dc6_name: str) -> tuple[Path, Path]:
    base = Path(out_dir) / f"{Path(dc6_name).stem}_overview"
    return base.with_suffix(".png"), base.with_suffix(".jpg")


def export_overview(image: QImage, out_dir: Path, dc6_name: str, jpg_quality: int) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png, jpg = output_paths(out_dir, dc6_name)
    if not image.save(str(png), "PNG"):
        raise OSError(f"Could not write {png}")
    if not image.convertToFormat(QImage.Format.Format_RGB888).save(str(jpg), "JPG", jpg_quality):
        raise OSError(f"Could not write {jpg}")
    return png, jpg
