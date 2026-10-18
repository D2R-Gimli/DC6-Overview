"""Dialogs: import size warning (before/after), import problems, Import All report, issues, About."""

from dataclasses import dataclass

import numpy as np
from core import APP_AUTHOR, APP_DATE, APP_NAME, APP_VERSION
from core.palette import Palette
from core.paths import LOGO_PATH
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from gui.widgets import frame_qimage, framed_pixmap

OK_GREEN, WARN_YELLOW, ERR_RED, GREY = "#3c9a3c", "#c09000", "#d04040", "#888888"


def _html_list(items: list[str]) -> str:
    return "".join(f"<li>{s}</li>" for s in items)


def _fit_zoom(w: int, h: int, box: int = 300) -> int:
    return max(1, min(16, box // max(w, h, 1)))


class ImportConfirmDialog(QDialog):
    """Before/after preview with OK / Abort; used when the size differs or there are other warnings."""

    def __init__(
        self,
        before: np.ndarray,
        after: np.ndarray,
        palette: Palette,
        file_name: str,
        frame_index: int,
        warnings: list[str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import – please confirm")
        lay = QVBoxLayout(self)
        msg = QLabel(
            f"<b>{file_name}</b> → frame <b>{frame_index:04d}</b><ul>{_html_list(warnings)}</ul>"
            "Press <b>OK</b> to import it anyway, or <b>Abort</b> to keep the current frame."
        )
        msg.setWordWrap(True)
        lay.addWidget(msg)
        zoom = _fit_zoom(max(before.shape[1], after.shape[1]), max(before.shape[0], after.shape[0]))
        grid = QGridLayout()
        for col, (title, px) in enumerate((("Before", before), ("After", after))):
            grid.addWidget(
                QLabel(f"<b>{title}</b> ({px.shape[1]}×{px.shape[0]})"), 0, col, Qt.AlignmentFlag.AlignCenter
            )
            view = QLabel()
            view.setPixmap(framed_pixmap(frame_qimage(px, palette), zoom))
            view.setAlignment(Qt.AlignmentFlag.AlignCenter)
            view.setMinimumSize(320, 320)
            view.setFrameShape(QFrame.Shape.StyledPanel)
            view.setStyleSheet("background: #202020;")
            grid.addWidget(view, 1, col)
        lay.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Abort)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Abort).clicked.connect(self.reject)
        lay.addWidget(buttons)


class ImportErrorDialog(QDialog):
    def __init__(self, file_name: str, errors: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import failed")
        lay = QVBoxLayout(self)
        label = QLabel(
            f"<b>{file_name}</b> can't be imported:<ul>{_html_list(errors)}</ul>Nothing has been changed."
        )
        label.setWordWrap(True)
        label.setMinimumWidth(520)
        lay.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


@dataclass(slots=True)
class ReportRow:
    file: str
    frame: str
    result: str  # OK / Warning / Error / Skipped
    details: str


class ImportAllReportDialog(QDialog):
    COLORS = {"OK": OK_GREEN, "Warning": WARN_YELLOW, "Error": ERR_RED, "Skipped": GREY}

    def __init__(self, folder: str, rows: list[ReportRow], importable: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import All – check report")
        self.resize(980, 460)
        counts = {k: sum(r.result == k for r in rows) for k in self.COLORS}
        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                f"Folder: <b>{folder}</b> — {len(rows)} file(s) checked: "
                f"<span style='color:{OK_GREEN}'>{counts['OK']} OK</span>, "
                f"<span style='color:{WARN_YELLOW}'>{counts['Warning']} warning(s)</span>, "
                f"<span style='color:{ERR_RED}'>{counts['Error']} error(s)</span>, {counts['Skipped']} skipped.<br>"
                "Nothing has been changed yet."
            )
        )
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["File", "Frame", "Result", "Details / how to fix"])
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setWordWrap(True)
        for r, row in enumerate(rows):
            for c, value in enumerate((row.file, row.frame, row.result, row.details)):
                item = QTableWidgetItem(value)
                if c == 2:
                    item.setForeground(QColor(self.COLORS.get(value, GREY)))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.resizeRowsToContents()
        lay.addWidget(table)
        buttons = QDialogButtonBox()
        text = (
            f"Import {importable} file(s)"
            if not counts["Error"]
            else f"Import {importable} valid file(s) only"
        )
        self.import_button = QPushButton(text)
        self.import_button.setEnabled(importable > 0)
        buttons.addButton(self.import_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class TextReportDialog(QDialog):
    def __init__(self, title: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 420)
        lay = QVBoxLayout(self)
        edit = QPlainTextEdit(text)
        edit.setReadOnly(True)
        lay.addWidget(edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        lay = QHBoxLayout(self)
        logo = QLabel()
        logo.setPixmap(
            QPixmap(str(LOGO_PATH)).scaledToHeight(150, Qt.TransformationMode.SmoothTransformation)
        )
        lay.addWidget(logo)
        info = QVBoxLayout()
        info.addWidget(
            QLabel(
                f"<h2>{APP_NAME}</h2>Version {APP_VERSION} · {APP_DATE}<br>made by <b>{APP_AUTHOR}</b><br><br>"
                "View, extract, import and overview<br>Diablo II <b>.dc6</b> files."
            )
        )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        info.addWidget(buttons)
        lay.addLayout(info)


class OffsetDialog(QDialog):
    """'Change Offsets' (like DC6 Creator): whole numbers, negative values allowed."""

    LIMIT = 1_000_000

    def __init__(self, frame_index: int, offset_x: int, offset_y: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Change Offsets – frame {frame_index:04d}")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.spin_x, self.spin_y = QSpinBox(), QSpinBox()
        for spin, value in ((self.spin_x, offset_x), (self.spin_y, offset_y)):
            spin.setRange(-self.LIMIT, self.LIMIT)
            spin.setValue(value)
            spin.setMinimumWidth(120)
        form.addRow("X Offset:", self.spin_x)
        form.addRow("Y Offset:", self.spin_y)
        lay.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.spin_x.selectAll()

    def values(self) -> tuple[int, int]:
        return self.spin_x.value(), self.spin_y.value()
