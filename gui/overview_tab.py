"""Overview tab: settings on the left, big live preview on the right, export PNG + JPG."""

from pathlib import Path

import numpy as np
from core.overview.layout import oversize_frames, standard_size
from core.overview.options import BORDER_PRESETS, CLASSIC_FONT, SCALES, OverviewOptions
from core.overview.pipeline import OverviewResult, build_overview, export_overview, output_paths
from core.overview.upscale import METHODS
from core.palette import Palette
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.settings import Settings
from gui.widgets import ColorButton, LimitedTextEdit, ZoomView

RENDER_DELAY_MS = 300


class _RenderSignals(QObject):
    done = Signal(int, object)  # generation, OverviewResult
    failed = Signal(int, str)


class _RenderJob(QRunnable):
    def __init__(
        self, gen: int, frames: list[np.ndarray], palette: Palette, opts: OverviewOptions, name: str
    ):
        super().__init__()
        self.gen, self.frames, self.palette, self.opts, self.name = gen, frames, palette, opts, name
        self.signals = _RenderSignals()

    def run(self) -> None:
        try:
            result = build_overview(self.frames, self.palette, self.opts, self.name)
        except Exception as e:  # report any render problem in the UI instead of crashing the worker
            self.signals.failed.emit(self.gen, str(e))
        else:
            self.signals.done.emit(self.gen, result)


class OverviewTab(QWidget):
    statusMessage = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.frames: list[np.ndarray] = []
        self.palette: Palette | None = None
        self.file_name = ""
        self._source_folder = ""
        self.result: OverviewResult | None = None
        self._gen = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._timer = QTimer(self, singleShot=True, interval=RENDER_DELAY_MS)
        self._timer.timeout.connect(self._start_render)
        self._build_ui(settings.overview_options())

    # ================================================================ UI
    def _build_ui(self, o: OverviewOptions) -> None:
        form = QVBoxLayout()

        src = QGroupBox("Source")
        sl = QFormLayout(src)
        self.l_source, self.l_count = QLabel("– (open a DC6 in the DC6 Viewer tab)"), QLabel("–")
        self.l_source.setWordWrap(True)
        sl.addRow("DC6:", self.l_source)
        sl.addRow("Frames:", self.l_count)
        form.addWidget(src)

        hdr = QGroupBox("Header text (max. 2 lines × 50 characters)")
        hl = QVBoxLayout(hdr)
        self.e_text = LimitedTextEdit("\n".join(t for t in (o.text_line1, o.text_line2)).rstrip("\n"))
        self.e_text.setPlaceholderText("Project Diablo 2\nSeason 14")
        hl.addWidget(self.e_text)
        form.addWidget(hdr)

        grid = QGroupBox("Grid")
        gl = QFormLayout(grid)
        self.s_cols, self.s_rows = QSpinBox(), QSpinBox()
        self.s_cols.setRange(1, 1000)
        self.s_rows.setRange(1, 100000)
        self.s_cols.setValue(o.columns)
        cr = QHBoxLayout()
        cr.addWidget(self.s_cols)
        cr.addWidget(QLabel("Rows:"))
        cr.addWidget(self.s_rows)
        gl.addRow("Columns:", cr)
        self.s_every = QSpinBox()
        self.s_every.setRange(0, 100000)
        self.s_every.setSpecialValueText("off")
        self.s_every.setPrefix("every ")
        self.s_every.setSuffix(" frames")
        self.s_every.setValue(o.number_every)
        self.s_every.setToolTip(
            "1 = a number above every frame, 5 = every 5th, 10 = every 10th, 0 = no numbers"
        )
        gl.addRow("Frame numbers:", self.s_every)
        self.c_font = QComboBox()
        self.c_font.addItem(CLASSIC_FONT)
        self.c_font.addItems(QFontDatabase.families())
        self.c_font.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.c_font.setMinimumContentsLength(14)
        self.c_font.setCurrentText(o.number_font if self.c_font.findText(o.number_font) >= 0 else "Tahoma")
        self.c_font.setToolTip(
            "Font of the frame numbers. Classic = the pixel digits of the old DC6 Overview"
        )
        gl.addRow("Number font:", self.c_font)
        self.s_font_size = QSpinBox()
        self.s_font_size.setRange(4, 40)
        self.s_font_size.setValue(o.number_size)
        self.s_font_size.setSuffix(" px")
        self.s_font_size.setToolTip("Size on the ×1 grid (doubled at ×2)")
        self.c_font_bold = QCheckBox("Bold")
        self.c_font_bold.setChecked(o.number_bold)
        fs = QHBoxLayout()
        fs.addWidget(self.s_font_size)
        fs.addWidget(self.c_font_bold)
        fs.addSpacing(10)
        fs.addWidget(QLabel("Colour:"))
        self.number_color_btn = ColorButton(o.number_rgb, "Frame number colour")
        fs.addWidget(self.number_color_btn)
        fs.addStretch()
        gl.addRow("Number size:", fs)
        self._font_controls_enabled()
        self.s_sx, self.s_sy, self.s_margin = QSpinBox(), QSpinBox(), QSpinBox()
        for s, v in ((self.s_sx, o.spacing_x), (self.s_sy, o.spacing_y), (self.s_margin, o.side_margin)):
            s.setRange(0, 200)
            s.setValue(v)
            s.setSuffix(" px")
        sp = QHBoxLayout()
        sp.addWidget(QLabel("X"))
        sp.addWidget(self.s_sx)
        sp.addWidget(QLabel("Y"))
        sp.addWidget(self.s_sy)
        gl.addRow("Spacing:", sp)
        gl.addRow("Side margin:", self.s_margin)
        self.c_collapse = QCheckBox("Spacing 0: neighbouring borders share one 1 px wall")
        self.c_collapse.setChecked(o.collapse_borders)
        gl.addRow(self.c_collapse)
        form.addWidget(grid)

        brd = QGroupBox("Border (1 px)")
        bl = QVBoxLayout(brd)
        self.c_border = QCheckBox("Draw a border around each graphic")
        self.c_border.setChecked(o.show_border)
        bl.addWidget(self.c_border)
        sw = QHBoxLayout()
        self.color_btn = ColorButton(o.border_rgb, "Border colour")
        for name, rgb in BORDER_PRESETS:
            b = QToolButton()
            b.setFixedSize(22, 22)
            b.setToolTip(name)
            b.setStyleSheet(f"QToolButton {{ background: rgb{rgb}; border: 1px solid #777; }}")
            b.clicked.connect(lambda _=False, c=rgb: self.color_btn.set_rgb(c))
            sw.addWidget(b)
        sw.addSpacing(8)
        sw.addWidget(QLabel("Custom:"))
        sw.addWidget(self.color_btn)
        sw.addStretch()
        bl.addLayout(sw)
        form.addWidget(brd)

        ov = QGroupBox("Oversize frames")
        ol = QVBoxLayout(ov)
        self.l_over = QLabel("–")
        self.l_over.setWordWrap(True)
        ol.addWidget(self.l_over)
        form.addWidget(ov)

        out = QGroupBox("Output")
        of = QFormLayout(out)
        self.c_method = QComboBox()
        for key, label in METHODS.items():
            self.c_method.addItem(label, key)
        self.c_method.setCurrentIndex(max(0, self.c_method.findData(o.upscale_method)))
        self.c_scale = QComboBox()
        for s in SCALES:
            self.c_scale.addItem(f"×{s}", s)
        self.c_scale.setCurrentIndex(max(0, self.c_scale.findData(o.scale)))
        mr = QHBoxLayout()
        mr.addWidget(self.c_method, 1)
        mr.addWidget(self.c_scale)
        of.addRow("Upscale:", mr)
        self.s_jpg = QSpinBox()
        self.s_jpg.setRange(50, 100)
        self.s_jpg.setValue(o.jpg_quality)
        of.addRow("JPG quality:", self.s_jpg)
        self.e_folder = QLineEdit(self.settings.output_dir)
        self.e_folder.setPlaceholderText("same folder as the DC6")
        b_browse = QPushButton("…")
        b_browse.setFixedWidth(30)
        b_browse.clicked.connect(self._browse_folder)
        fr = QHBoxLayout()
        fr.addWidget(self.e_folder, 1)
        fr.addWidget(b_browse)
        of.addRow("Folder:", fr)
        form.addWidget(out)

        self.btn_export = QPushButton("Export PNG + JPG")
        self.btn_export.setMinimumHeight(40)
        self.btn_export.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_export.clicked.connect(self.export)
        form.addStretch()

        left = QWidget()
        left.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_col = QVBoxLayout()  # export button stays visible below the scrolling settings
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.addWidget(scroll, 1)
        left_col.addWidget(self.btn_export)
        left_w = QWidget()
        left_w.setLayout(left_col)
        left_w.setFixedWidth(400)

        self.view = ZoomView()
        tools = QHBoxLayout()
        for text, fn in (
            ("−", lambda: self.view.zoom_by(0.8)),
            ("+", lambda: self.view.zoom_by(1.25)),
            ("Fit", self.view.fit),
            ("100 %", self.view.actual_size),
        ):
            b = QPushButton(text)
            b.setFixedWidth(60)
            b.clicked.connect(fn)
            tools.addWidget(b)
        self.l_zoom = QLabel()
        tools.addWidget(self.l_zoom)
        tools.addStretch()
        self.l_info = QLabel()
        tools.addWidget(self.l_info)
        self.view.zoomChanged.connect(lambda z: self.l_zoom.setText(f"  {z * 100:.0f} %"))
        right = QVBoxLayout()
        right.addLayout(tools)
        right.addWidget(self.view, 1)
        right_w = QWidget()
        right_w.setLayout(right)

        lay = QHBoxLayout(self)
        lay.addWidget(left_w)
        lay.addWidget(right_w, 1)

        self.s_cols.valueChanged.connect(self._cols_changed)
        self.s_rows.valueChanged.connect(self._rows_changed)
        for s in (self.s_every, self.s_sx, self.s_sy, self.s_margin):
            s.valueChanged.connect(self.schedule)
        self.s_jpg.valueChanged.connect(self._save_options)
        self.e_text.textChanged.connect(self.schedule)
        self.c_font.currentIndexChanged.connect(self._font_controls_enabled)
        self.s_font_size.valueChanged.connect(self.schedule)
        self.number_color_btn.colorChanged.connect(self.schedule)
        for c in (self.c_method, self.c_scale, self.c_font):
            c.currentIndexChanged.connect(self.schedule)
        for c in (self.c_collapse, self.c_border, self.c_font_bold):
            c.toggled.connect(self.schedule)
        self.color_btn.colorChanged.connect(self.schedule)
        self.e_folder.editingFinished.connect(
            lambda: setattr(self.settings, "output_dir", self.e_folder.text())
        )
        self._update_enabled()

    def options(self) -> OverviewOptions:
        return OverviewOptions(
            columns=self.s_cols.value(),
            number_every=self.s_every.value(),
            spacing_x=self.s_sx.value(),
            spacing_y=self.s_sy.value(),
            side_margin=self.s_margin.value(),
            collapse_borders=self.c_collapse.isChecked(),
            show_border=self.c_border.isChecked(),
            border_rgb=self.color_btn.rgb,
            upscale_method=self.c_method.currentData(),
            scale=self.c_scale.currentData(),
            number_font=self.c_font.currentText(),
            number_size=self.s_font_size.value(),
            number_bold=self.c_font_bold.isChecked(),
            number_rgb=self.number_color_btn.rgb,
            text_line1=self.e_text.lines()[0],
            text_line2=self.e_text.lines()[1],
            jpg_quality=self.s_jpg.value(),
        )

    def _font_controls_enabled(self) -> None:
        vector = self.c_font.currentText() != CLASSIC_FONT
        self.s_font_size.setEnabled(vector)
        self.c_font_bold.setEnabled(vector)

    def _save_options(self) -> None:
        self.settings.set_overview_options(self.options())

    def _update_enabled(self) -> None:
        self.btn_export.setEnabled(bool(self.frames) and self.result is not None)

    # ================================================================ source
    def set_source(
        self, frames: list[np.ndarray], palette: Palette, file_name: str, folder: str = ""
    ) -> None:
        self.frames, self.palette, self.file_name = frames, palette, file_name
        self._source_folder = folder
        if not frames:
            self.l_source.setText("– (open a DC6 in the DC6 Viewer tab)")
            self.l_count.setText("–")
            self.l_over.setText("–")
            self.result = None
            self.view.clear_image()
            self.l_info.setText("")
            self._update_enabled()
            return
        self.l_source.setText(f"{file_name}  (from DC6 Viewer, palette {palette.name})")
        self.l_count.setText(str(len(frames)))
        std = standard_size(frames)
        over = oversize_frames(frames, std)
        self.l_over.setText(
            f"Standard size {std[0]}×{std[1]}. "
            + (
                f"{len(over)} bigger: {', '.join(map(str, over[:30]))}{' …' if len(over) > 30 else ''}<br>"
                "<i>Shown cut to the standard size (keep the top, cut left/right/bottom) with a red cross.</i>"
                if over
                else "No oversize frames."
            )
        )
        self._cols_changed()

    def _cols_changed(self) -> None:
        if self.frames:
            self.s_rows.blockSignals(True)
            self.s_rows.setValue(-(-len(self.frames) // self.s_cols.value()))
            self.s_rows.blockSignals(False)
        self.schedule()

    def _rows_changed(self) -> None:
        if self.frames:
            self.s_cols.blockSignals(True)
            self.s_cols.setValue(-(-len(self.frames) // self.s_rows.value()))
            self.s_cols.blockSignals(False)
        self.schedule()

    # ================================================================ rendering
    def schedule(self) -> None:
        self._save_options()
        if self.frames:
            self.l_info.setText("rendering…")
            self._timer.start()

    def _start_render(self) -> None:
        if not self.frames or self.palette is None:
            return
        self._gen += 1
        job = _RenderJob(self._gen, list(self.frames), self.palette, self.options(), self.file_name)
        job.signals.done.connect(self._render_done)
        job.signals.failed.connect(self._render_failed)
        self._pool.start(job)

    def _render_done(self, gen: int, result: OverviewResult) -> None:
        if gen != self._gen:
            return  # a newer render is on its way
        self.result = result
        self.view.set_image(result.image)
        g = result.geometry
        self.l_info.setText(
            f"Final image: {result.image.width()} × {result.image.height()} px   ({g.cols} × {g.rows} grid)"
        )
        self._update_enabled()

    def _render_failed(self, gen: int, message: str) -> None:
        if gen == self._gen:
            self.l_info.setText(f"<span style='color:#d04040'>Render failed: {message}</span>")

    def wait_for_render(self) -> None:
        """Render synchronously (used by tests and screenshots)."""
        self._timer.stop()
        self._start_render()
        self._pool.waitForDone()
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

    # ================================================================ export
    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Output folder", self.e_folder.text() or self._source_folder
        )
        if folder:
            self.e_folder.setText(folder)
            self.settings.output_dir = folder

    def export(self) -> None:
        if self.result is None or not self.frames:
            return
        if self._timer.isActive():
            self.wait_for_render()
        folder = Path(self.e_folder.text() or getattr(self, "_source_folder", "") or ".")
        png, jpg = output_paths(folder, self.file_name)
        existing = [p.name for p in (png, jpg) if p.exists()]
        if (
            existing
            and QMessageBox.question(
                self, "Overwrite?", f"{' and '.join(existing)} already exist in {folder}. Overwrite?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            png, jpg = export_overview(self.result.image, folder, self.file_name, self.s_jpg.value())
        except OSError as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        size = f"{self.result.image.width()} × {self.result.image.height()} px"
        self.statusMessage.emit(f"Exported {png.name} and {jpg.name} ({size}) to {folder}")
        QMessageBox.information(self, "Export done", f"Saved ({size}):<br>{png}<br>{jpg}")
