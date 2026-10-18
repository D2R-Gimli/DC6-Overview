"""Header banner drawn with QPainter at the final resolution (needs a QGuiApplication)."""

from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from core import APP_AUTHOR
from core.paths import LOGO_PATH

HEADER_UNITS = 100  # layout is designed for a 100 px high header (= ×2 scale)
BG = QColor(86, 86, 86)
GOLD = QColor("#FFC74B")
LABEL = QColor("#FDC080")
ORANGE = QColor("#F17141")
WHITE = QColor("white")
DIM = QColor(176, 176, 176)  # less prominent detail text, e.g. the oversize frame list
FONT_FAMILY = "Arial"
MAX_OVERSIZE_LISTED = 12


@dataclass(slots=True)
class HeaderInfo:
    file_name: str
    frame_count: int
    oversize: list[int]
    created: str  # DD.MM.YYYY
    line1: str = ""
    line2: str = ""


def _font(px: float, bold: bool = False) -> QFont:
    f = QFont(FONT_FAMILY)
    f.setPixelSize(max(1, round(px)))
    f.setBold(bold)
    return f


def oversize_text(oversize: list[int]) -> tuple[str, str]:
    """('6', ' (1550, 1551, …)'): the count and the (dimmed) list."""
    if not oversize:
        return "0", ""
    shown = ", ".join(map(str, oversize[:MAX_OVERSIZE_LISTED]))
    more = ", …" if len(oversize) > MAX_OVERSIZE_LISTED else ""
    return str(len(oversize)), f" ({shown}{more})"


def compose(body: QImage, info: HeaderInfo, header_h: int, gap: int) -> QImage:
    """Header (grey) + black gap + body. Widens the canvas if the header text needs more room."""
    u = header_h / HEADER_UNITS
    f_title, f_name, f_free = _font(32 * u, True), _font(32 * u), _font(26 * u)
    f_label, f_value = _font(22 * u, True), _font(22 * u)
    fm_title, fm_name, fm_free = QFontMetrics(f_title), QFontMetrics(f_name), QFontMetrics(f_free)
    fm_label, fm_value = QFontMetrics(f_label), QFontMetrics(f_value)

    def lv_width(label: str, value: str, extra: str = "") -> int:
        return fm_label.horizontalAdvance(label + " ") + fm_value.horizontalAdvance(value + extra)

    created_lines = [("Created:", info.created, ""), ("Creator:", APP_AUTHOR, "")]
    info_lines = [("Graphics:", str(info.frame_count), ""), ("Oversize:", *oversize_text(info.oversize))]
    free_lines = [line for line in (info.line1, info.line2) if line.strip()]

    # Columns as in the example (positions in header units), pushed right when text is wider
    x_a = 110 * u
    a_end = x_a + max(fm_title.horizontalAdvance("Overview:"), fm_name.horizontalAdvance(info.file_name))
    free_w = max([fm_free.horizontalAdvance(line) for line in free_lines] + [1])
    b_center = max(500 * u, a_end + 40 * u + free_w / 2)
    x_c = max(720 * u, b_center + free_w / 2 + 50 * u)
    c_end = x_c + max(lv_width(*line) for line in info_lines)
    x_d = max(1390 * u, c_end + 80 * u)
    d_end = x_d + max(lv_width(*line) for line in created_lines)
    width = max(body.width(), int(d_end + 40 * u))

    out = QImage(width, header_h + gap + body.height(), QImage.Format.Format_RGB32)
    out.fill(QColor(0, 0, 0))
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(0, header_h + gap, body)
    p.fillRect(0, 0, width, header_h, BG)

    logo = QImage(str(LOGO_PATH))
    if not logo.isNull():
        lh = int(92 * u)
        lw = int(logo.width() * lh / logo.height())
        p.drawImage(QRect(int(8 * u), int(4 * u), lw, lh), logo)

    def text(x: float, y: float, s: str, font: QFont, color: QColor) -> float:
        p.setFont(font)
        p.setPen(color)
        p.drawText(int(x), int(y), s)
        return x + QFontMetrics(font).horizontalAdvance(s)

    def label_value(x: float, y: float, label: str, value: str, extra: str = "") -> None:
        x = text(x, y, label + " ", f_label, LABEL)
        x = text(x, y, value, f_value, WHITE)
        if extra:
            text(x, y, extra, f_value, DIM)

    text(x_a, 38 * u, "Overview:", f_title, GOLD)
    text(x_a, 76 * u, info.file_name, f_name, WHITE)
    p.setFont(f_free)
    p.setPen(ORANGE)
    top = 14 if len(free_lines) == 2 else 31  # a single line is centred vertically
    for k, line in enumerate(free_lines):
        rect = QRect(
            int(b_center - free_w / 2 - 10 * u), int((top + k * 34) * u), int(free_w + 20 * u), int(34 * u)
        )
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, line)
    for k, line in enumerate(info_lines):
        label_value(x_c, (38 + 28 * k) * u, *line)
    for k, line in enumerate(created_lines):
        label_value(x_d, (38 + 28 * k) * u, *line)
    p.end()
    return out
