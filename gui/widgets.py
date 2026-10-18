"""Reusable widgets: indexed frame → pixmap, pixel-exact zoom view, colour button, pan/zoom preview."""

import numpy as np
from core.palette import Palette
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
)

VIEW_BG = QColor(32, 32, 32)  # transparent pixels show this background
FRAME_LINE = QColor(150, 150, 150)  # 1 px line around the frame area

ROLE_NUMBER = Qt.ItemDataRole.UserRole  # frame list: "0004"
ROLE_DETAIL = Qt.ItemDataRole.UserRole + 1  # "(16×32)"
ROLE_KIND = Qt.ItemDataRole.UserRole + 2  # "", "big" or "blank"


def frame_qimage(pixels: np.ndarray, palette: Palette) -> QImage:
    px = np.ascontiguousarray(pixels, np.uint8)
    h, w = px.shape
    img = QImage(px.data, w, h, w, QImage.Format.Format_Indexed8).copy()
    img.setColorTable(palette.argb_table())
    return img


def framed_pixmap(img: QImage, zoom: int) -> QPixmap:
    """Image scaled by an integer factor (nearest) on a plain background, with a 1 px line around
    the frame area so its size and transparent edges are visible."""
    w, h = img.width() * zoom, img.height() * zoom
    pm = QPixmap(w + 2, h + 2)
    pm.fill(VIEW_BG)
    p = QPainter(pm)
    p.setPen(FRAME_LINE)
    p.drawRect(0, 0, w + 1, h + 1)
    if w and h:
        p.drawImage(QRect(1, 1, w, h), img)
    p.end()
    return pm


class FrameItemDelegate(QStyledItemDelegate):
    """Frame list row: thumbnail, bold frame number, dimmed size."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.icon = QIcon()
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        rect = option.rect
        x = rect.left() + 4
        pm = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pm, QPixmap) and not pm.isNull():
            painter.drawPixmap(x, rect.top() + (rect.height() - pm.height()) // 2, pm)
            x += pm.width()
        x += 8
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        kind = index.data(ROLE_KIND) or ""
        text_color = opt.palette.highlightedText().color() if selected else opt.palette.text().color()
        number_color = QColor("#d05030") if kind == "big" and not selected else text_color
        detail_color = QColor(225, 225, 225) if selected else QColor(130, 130, 130)

        font = QFont(opt.font)
        font.setBold(True)
        painter.save()
        painter.setFont(font)
        painter.setPen(number_color)
        text_rect = QRect(x, rect.top(), rect.right() - x, rect.height())
        number = index.data(ROLE_NUMBER) or ""
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, number)
        x += QFontMetrics(font).horizontalAdvance(number + "  ")
        font.setBold(False)
        font.setItalic(kind == "blank")
        painter.setFont(font)
        painter.setPen(detail_color)
        painter.drawText(
            QRect(x, rect.top(), rect.right() - x, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            index.data(ROLE_DETAIL) or "",
        )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: N802 (Qt API)
        pm = index.data(Qt.ItemDataRole.DecorationRole)
        h = pm.height() if isinstance(pm, QPixmap) else 0
        return QSize(180, max(h, QFontMetrics(option.font).height()) + 6)


class PixelView(QScrollArea):
    """Scrollable, integer-zoomed frame view."""

    def __init__(self) -> None:
        super().__init__()
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self._label)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background: #202020; } QLabel { background: #202020; }")

    def show_image(self, img: QImage | None, zoom: int) -> None:
        if img is None:
            self._label.clear()
        else:
            self._label.setPixmap(framed_pixmap(img, zoom))


class ColorButton(QToolButton):
    colorChanged = Signal(tuple)

    def __init__(self, rgb: tuple[int, int, int], title: str = "Choose colour") -> None:
        super().__init__()
        self._rgb = tuple(rgb)
        self._title = title
        self.setFixedSize(40, 24)
        self.setToolTip("Click to open the colour wheel")
        self.clicked.connect(self._pick)
        self._refresh()

    @property
    def rgb(self) -> tuple[int, int, int]:
        return self._rgb  # type: ignore[return-value]

    def set_rgb(self, rgb: tuple[int, int, int]) -> None:
        rgb = tuple(int(v) for v in rgb)
        if rgb != self._rgb:
            self._rgb = rgb
            self._refresh()
            self.colorChanged.emit(rgb)

    def _refresh(self) -> None:
        self.setStyleSheet(f"QToolButton {{ background: rgb{self._rgb}; border: 1px solid #888; }}")

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(*self._rgb), self, self._title)
        if c.isValid():
            self.set_rgb((c.red(), c.green(), c.blue()))


class ZoomView(QGraphicsView):
    """Large preview: mouse wheel zooms, drag pans."""

    zoomChanged = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self._item)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QColor(32, 32, 32))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._has_image = False

    def set_image(self, img: QImage) -> None:
        first = not self._has_image
        self._item.setPixmap(QPixmap.fromImage(img))
        self.scene().setSceneRect(self._item.boundingRect())
        self._has_image = True
        if first:
            self.fit()

    def clear_image(self) -> None:
        self._item.setPixmap(QPixmap())
        self._has_image = False

    def zoom_by(self, factor: float) -> None:
        self.scale(factor, factor)
        self.zoomChanged.emit(self.transform().m11())

    def fit(self) -> None:
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
        self.zoomChanged.emit(self.transform().m11())

    def actual_size(self) -> None:
        self.resetTransform()
        self.zoomChanged.emit(1.0)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8)


class LimitedTextEdit(QPlainTextEdit):
    """Multi-line input limited to `max_lines` lines of `max_chars` characters (header free text)."""

    def __init__(self, text: str = "", max_lines: int = 2, max_chars: int = 50) -> None:
        super().__init__()
        self.max_lines, self.max_chars = max_lines, max_chars
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabChangesFocus(True)
        line_h = QFontMetrics(self.font()).lineSpacing()
        self.setFixedHeight(line_h * max_lines + 14)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )  # no extra height in layouts
        self.setPlainText(text)
        self.textChanged.connect(self._enforce)

    def lines(self) -> list[str]:
        return (self.toPlainText().split("\n") + [""] * self.max_lines)[: self.max_lines]

    def _enforce(self) -> None:
        text = self.toPlainText()
        lines = text.split("\n")
        limited = "\n".join(line[: self.max_chars] for line in lines[: self.max_lines])
        if limited != text:
            cursor = self.textCursor()
            pos = min(cursor.position(), len(limited))
            self.blockSignals(True)
            self.setPlainText(limited)
            cursor = self.textCursor()
            cursor.setPosition(pos)
            self.setTextCursor(cursor)
            self.blockSignals(False)
            self.textChanged.emit()
