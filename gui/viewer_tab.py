"""DC6 Viewer tab: browse/zoom frames, export/import single or all frames, blank frames, save."""

import json
from pathlib import Path

import numpy as np
from core.dc6 import DC6Error, DC6File, Level, load_dc6, save_dc6
from core.imageio import (
    EXPORT_FORMATS,
    IMPORT_EXTENSIONS,
    export_frame,
    frame_filename,
    parse_frame_filename,
)
from core.import_check import check_image
from core.overview.render import thumbnail
from core.palette import Palette, builtin_palettes
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gui.dialogs import (
    ERR_RED,
    OK_GREEN,
    WARN_YELLOW,
    ImportAllReportDialog,
    ImportConfirmDialog,
    ImportErrorDialog,
    OffsetDialog,
    ReportRow,
    TextReportDialog,
)
from gui.settings import Settings
from gui.widgets import (
    ROLE_DETAIL,
    ROLE_KIND,
    ROLE_NUMBER,
    FrameItemDelegate,
    PixelView,
    frame_qimage,
    framed_pixmap,
)

ZOOM_MIN, ZOOM_MAX = 1, 32
CUSTOM_PALETTE = "Load palette file…"
EXPORT_FILTERS = {name: f"{name} image (*{ext})" for name, ext in EXPORT_FORMATS.items()}


class ViewerTab(QWidget):
    documentChanged = Signal()  # frames or palette changed → overview must re-render
    stateChanged = Signal()  # file name / modified flag changed → window title
    statusMessage = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.dc6: DC6File | None = None
        self.path: Path | None = None
        self.modified = False
        self.zoom = settings.default_zoom
        self._thumb_zoom = 2
        self.palettes = builtin_palettes()
        self.palette = Palette.load(self.palettes.get(settings.palette, self.palettes["act1"]))
        self._build_ui()
        self._update_enabled()

    # ================================================================ UI
    def _build_ui(self) -> None:
        top = QHBoxLayout()
        self.btn_open, self.btn_save, self.btn_save_as = (
            QPushButton("Open…"),
            QPushButton("Save"),
            QPushButton("Save As…"),
        )
        self.btn_open.clicked.connect(lambda: self.open_file())
        self.btn_save.clicked.connect(self.save)
        self.btn_save_as.clicked.connect(self.save_as)
        for b in (self.btn_open, self.btn_save, self.btn_save_as):
            top.addWidget(b)
        top.addSpacing(16)
        top.addWidget(QLabel("Palette:"))
        self.pal_combo = QComboBox()
        self.pal_combo.addItems([*self.palettes, CUSTOM_PALETTE])
        self.pal_combo.setCurrentText(self.palette.name)
        self.pal_combo.activated.connect(self._palette_selected)
        top.addWidget(self.pal_combo)
        top.addStretch()
        top.addWidget(QLabel("Zoom:"))
        self.btn_zoom_out, self.btn_zoom_in = QPushButton("−"), QPushButton("+")
        for b in (self.btn_zoom_out, self.btn_zoom_in):
            b.setFixedWidth(34)
        self.btn_zoom_out.clicked.connect(lambda: self.set_zoom(self.zoom - 1))
        self.btn_zoom_in.clicked.connect(lambda: self.set_zoom(self.zoom + 1))
        self.zoom_label = QLabel()
        self.zoom_label.setMinimumWidth(110)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_default_zoom = QPushButton("Set as default zoom")
        self.btn_default_zoom.clicked.connect(self._make_default_zoom)
        for w in (self.btn_zoom_out, self.zoom_label, self.btn_zoom_in, self.btn_default_zoom):
            top.addWidget(w)

        self.list = QListWidget()
        self.list.setMinimumWidth(210)
        self.list.setUniformItemSizes(True)
        self.list.setItemDelegate(FrameItemDelegate(self.list))
        self.list.currentRowChanged.connect(self._show_frame)

        self.view = PixelView()

        frame_box = QGroupBox("Frame")
        ff = QFormLayout(frame_box)
        self.l_index, self.l_size, self.l_offset_x, self.l_offset_y, self.l_state = (
            QLabel() for _ in range(5)
        )
        self.l_state.setWordWrap(True)
        ff.addRow("Index:", self.l_index)
        ff.addRow("Size:", self.l_size)
        ff.addRow("Offset X:", self.l_offset_x)
        ff.addRow("Offset Y:", self.l_offset_y)
        ff.addRow("State:", self.l_state)
        self.btn_offsets = QPushButton("Change Offsets…")
        self.btn_offsets.setToolTip("Edit the X / Y offset of the selected frame")
        self.btn_offsets.clicked.connect(self.change_offsets)
        ff.addRow("", self.btn_offsets)
        file_box = QGroupBox("File")
        fl = QFormLayout(file_box)
        self.l_file, self.l_frames, self.l_dirs, self.l_std, self.l_over, self.l_valid = (
            QLabel() for _ in range(6)
        )
        for lab in (self.l_file, self.l_over, self.l_valid):
            lab.setWordWrap(True)
        fl.addRow("File:", self.l_file)
        fl.addRow("Frames:", self.l_frames)
        fl.addRow("Directions:", self.l_dirs)
        fl.addRow("Standard size:", self.l_std)
        fl.addRow("Oversize:", self.l_over)
        fl.addRow("Validation:", self.l_valid)
        self.btn_issues = QPushButton("Details…")
        self.btn_issues.clicked.connect(self._show_issues)
        fl.addRow("", self.btn_issues)
        self.btn_export = QPushButton("Export…")
        self.btn_export_all = QPushButton("Export All…")
        self.btn_import = QPushButton("Import…")
        self.btn_import_all = QPushButton("Import All…")
        self.btn_add_blank = QPushButton("+ Add new frame")
        self.btn_remove_last = QPushButton("− Remove last frame")

        side = QVBoxLayout()
        side.addWidget(frame_box)
        side.addWidget(file_box)
        side.addSpacing(6)
        for b in (self.btn_export, self.btn_export_all, self.btn_import, self.btn_import_all):
            b.setMinimumHeight(30)
            side.addWidget(b)
        side.addStretch()
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(280)

        split = QSplitter()
        split.addWidget(self.list)
        split.addWidget(self.view)
        split.addWidget(side_w)
        split.setStretchFactor(1, 1)

        bottom = QHBoxLayout()
        self.btn_export.clicked.connect(self.export_current)
        self.btn_export_all.clicked.connect(self.export_all)
        self.btn_import.clicked.connect(self.import_current)
        self.btn_import_all.clicked.connect(self.import_all)
        self.btn_add_blank.clicked.connect(self.add_blank_frame)
        self.btn_remove_last.clicked.connect(self.remove_last_frame)
        tips = {
            self.btn_export: "Export the shown frame (choose file type and path)",
            self.btn_export_all: "Export every frame as 0000.ext, 0001.ext, … into a folder",
            self.btn_import: "Replace the selected frame with an image file (checked first)",
            self.btn_import_all: "Replace frames from a folder: 0000.bmp → frame 0, 0004.pcx → frame 4, …",
            self.btn_add_blank: "Append a new, empty frame at the end (only saved once a graphic is imported)",
            self.btn_remove_last: "Remove the last frame of the DC6",
        }
        for b in (self.btn_add_blank, self.btn_remove_last):
            b.setMinimumHeight(30)
            bottom.addWidget(b)
        for b, tip in tips.items():
            b.setToolTip(tip)
        bottom.addStretch()

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addLayout(bottom)
        self._update_zoom_label()

    def _update_enabled(self) -> None:
        has = self.dc6 is not None
        for b in (
            self.btn_save,
            self.btn_save_as,
            self.btn_export,
            self.btn_export_all,
            self.btn_import,
            self.btn_import_all,
            self.btn_add_blank,
            self.btn_remove_last,
            self.btn_issues,
            self.btn_offsets,
        ):
            b.setEnabled(has)

    # ================================================================ document
    @property
    def file_name(self) -> str:
        return self.path.name if self.path else "untitled.dc6"

    def overview_frames(self) -> list[np.ndarray]:
        return [] if self.dc6 is None else [f.pixels for f in self.dc6.frames if not f.blank]

    def _set_modified(self, value: bool) -> None:
        self.modified = value
        self.stateChanged.emit()

    def maybe_save(self) -> bool:
        """True when it is OK to discard the current document."""
        if self.dc6 is None or not self.modified:
            return True
        r = QMessageBox.question(
            self,
            "Unsaved changes",
            f"{self.file_name} has unsaved changes. Save them?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def open_file(self, path: str | Path | None = None) -> bool:
        if not self.maybe_save():
            return False
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Open DC6", self.settings.last_dir("open"), "DC6 files (*.dc6);;All files (*)"
            )
            if not path:
                return False
        path = Path(path)
        try:
            dc6 = load_dc6(path)
        except (OSError, DC6Error) as e:
            QMessageBox.critical(self, "Cannot open file", f"<b>{path.name}</b> can't be opened:<br><br>{e}")
            return False
        self.settings.set_last_dir("open", str(path.parent))
        self.dc6, self.path = dc6, path
        self.zoom = self.settings.default_zoom
        self._update_zoom_label()
        self._rebuild_list()
        self._update_enabled()
        self._set_modified(False)
        self.documentChanged.emit()
        errors = sum(i.level == Level.WARNING for i in dc6.issues)
        self.statusMessage.emit(
            f"{path.name} loaded – {dc6.frame_count} frames"
            + (f", {errors} warning(s)" if errors else ", validation OK")
        )
        return True

    def save(self) -> bool:
        if self.dc6 is None:
            return False
        if self.path is None:
            return self.save_as()
        return self._save_to(self.path)

    def save_as(self) -> bool:
        if self.dc6 is None:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Save DC6 as", str(self.path or ""), "DC6 files (*.dc6)")
        if not path:
            return False
        path = Path(path)
        if path.suffix.lower() != ".dc6":
            path = path.with_suffix(".dc6")
        return self._save_to(path)

    def _save_to(self, path: Path) -> bool:
        assert self.dc6 is not None
        gaps = self.dc6.has_blank_gaps()
        if gaps:
            names = ", ".join(f"{i:04d}" for i in gaps[:10]) + (" …" if len(gaps) > 10 else "")
            w, h = self.dc6.standard_size()
            r = QMessageBox.question(
                self,
                "Blank frames",
                f"Frame(s) {names} are still blank, but frames after them contain graphics.<br>"
                f"A DC6 can't have gaps, so they will be saved as <b>empty transparent {w}×{h} frames</b>.<br><br>"
                "Continue?",
            )
            if r != QMessageBox.StandardButton.Yes:
                return False
        try:
            bak = save_dc6(self.dc6, path)
        except (OSError, DC6Error, ValueError) as e:
            QMessageBox.critical(self, "Save failed", f"Could not save <b>{path.name}</b>:<br><br>{e}")
            return False
        self.path = path
        self._rebuild_list()
        self._set_modified(False)
        self.documentChanged.emit()
        self.statusMessage.emit(f"Saved {path}" + (f" (backup of the original: {bak.name})" if bak else ""))
        return True

    # ================================================================ list & preview
    def _fill_item(self, item: QListWidgetItem, i: int) -> None:
        """Data for FrameItemDelegate: thumbnail, bold number, dimmed size."""
        assert self.dc6 is not None
        fr = self.dc6.frames[i]
        if self.dc6.directions > 1:
            d, f = divmod(i, self.dc6.frames_per_dir)
            number = f"D{d:02d} F{f:03d}"
            extra = f"  #{i:04d}"
        else:
            number, extra = f"{i:04d}", ""
        std = self.dc6.standard_size()
        big = fr.width > std[0] or fr.height > std[1]
        if fr.blank:
            kind, detail = "blank", "(new, empty)"
        else:
            kind, detail = ("big" if big else ""), f"({fr.width}×{fr.height})" + ("  BIG" if big else "")
        thumb, _ = thumbnail(fr.pixels, std)
        item.setData(
            Qt.ItemDataRole.DecorationRole, framed_pixmap(frame_qimage(thumb, self.palette), self._thumb_zoom)
        )
        item.setData(ROLE_NUMBER, number)
        item.setData(ROLE_DETAIL, detail + extra)
        item.setData(ROLE_KIND, kind)
        item.setText(f"{number} {detail}")  # used for keyboard search / accessibility

    def _make_item(self, i: int) -> QListWidgetItem:
        item = QListWidgetItem()
        self._fill_item(item, i)
        return item

    def _rebuild_list(self) -> None:
        row = max(0, self.list.currentRow())
        self.list.blockSignals(True)
        self.list.clear()
        if self.dc6 is not None:
            w, h = self.dc6.standard_size()
            # thumbnails twice as big as before: 16×32 → 32×64
            self._thumb_zoom = max(1, min(64 // max(h, 1), 96 // max(w, 1)))
            for i in range(self.dc6.frame_count):
                self.list.addItem(self._make_item(i))
        self.list.blockSignals(False)
        if self.dc6 is not None and self.dc6.frame_count:
            self.list.setCurrentRow(min(row, self.dc6.frame_count - 1))
            self._show_frame(self.list.currentRow())
        else:
            self.view.show_image(None, 1)
        self._update_file_info()

    def _refresh_item(self, i: int) -> None:
        self._fill_item(self.list.item(i), i)

    def _show_frame(self, i: int) -> None:
        if self.dc6 is None or not 0 <= i < self.dc6.frame_count:
            return
        fr = self.dc6.frames[i]
        self.view.show_image(frame_qimage(fr.pixels, self.palette), self.zoom)
        self.l_index.setText(f"{i}  ({i:04d})")
        self.l_size.setText(f"{fr.width} × {fr.height}" + ("  (standard size)" if fr.blank else ""))
        self.l_offset_x.setText(str(fr.offset_x))
        self.l_offset_y.setText(str(fr.offset_y))
        w, h = self.dc6.standard_size()
        if fr.blank:
            state = f"<span style='color:{WARN_YELLOW}'>blank – not saved until a graphic is imported</span>"
        elif fr.width > w or fr.height > h:
            state = f"<span style='color:{ERR_RED}'><b>oversize</b> (bigger than {w}×{h})</span>"
        elif fr.encoded is None:
            state = f"<span style='color:{WARN_YELLOW}'>changed (not saved yet)</span>"
        else:
            state = "ok"
        self.l_state.setText(state)

    def _update_file_info(self) -> None:
        dc6 = self.dc6
        if dc6 is None:
            for lab in (self.l_file, self.l_frames, self.l_dirs, self.l_std, self.l_over, self.l_valid):
                lab.setText("–")
            return
        blank = sum(f.blank for f in dc6.frames)
        w, h = dc6.standard_size()
        over = [i for i, f in enumerate(dc6.frames) if not f.blank and (f.width > w or f.height > h)]
        self.l_file.setText(self.file_name)
        self.l_frames.setText(
            f"{dc6.frame_count - blank}" + (f"  + {blank} blank (unsaved)" if blank else "")
        )
        self.l_dirs.setText(f"{dc6.directions} × {dc6.frames_per_dir} frames")
        self.l_std.setText(f"{w} × {h}")
        self.l_over.setText(
            f"{len(over)}"
            + (f": {', '.join(map(str, over[:20]))}" if over else "")
            + (" …" if len(over) > 20 else "")
        )
        errors = [i for i in dc6.issues if i.level == Level.ERROR]
        warns = [i for i in dc6.issues if i.level == Level.WARNING]
        if not errors and not warns:
            self.l_valid.setText(f"<span style='color:{OK_GREEN}'>OK</span> – no problems found")
        else:
            color = ERR_RED if errors else WARN_YELLOW
            self.l_valid.setText(
                f"<span style='color:{color}'>{len(errors)} error(s), {len(warns)} warning(s)</span>"
            )

    def _show_issues(self) -> None:
        if self.dc6 is None:
            return
        text = "\n".join(str(i) for i in self.dc6.issues) or "No problems found."
        TextReportDialog(f"Validation – {self.file_name}", text, self).exec()

    # ================================================================ zoom & palette
    def set_zoom(self, zoom: int) -> None:
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        self._update_zoom_label()
        self._show_frame(self.list.currentRow())

    def _update_zoom_label(self) -> None:
        default = " (default)" if self.zoom == self.settings.default_zoom else ""
        self.zoom_label.setText(f"{self.zoom * 100} %{default}")

    def _make_default_zoom(self) -> None:
        self.settings.default_zoom = self.zoom
        self._update_zoom_label()
        self.statusMessage.emit(f"Default zoom set to {self.zoom * 100} %")

    def _palette_selected(self) -> None:
        name = self.pal_combo.currentText()
        if name == CUSTOM_PALETTE:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Load palette",
                self.settings.last_dir("palette"),
                "Palettes (*.dat *.pal *.act);;All files (*)",
            )
            if not path:
                self.pal_combo.setCurrentText(self.palette.name)
                return
            try:
                pal = Palette.load(Path(path))
            except (OSError, ValueError) as e:
                QMessageBox.critical(self, "Palette", str(e))
                self.pal_combo.setCurrentText(self.palette.name)
                return
            self.settings.set_last_dir("palette", str(Path(path).parent))
            self.palettes[pal.name] = Path(path)
            if self.pal_combo.findText(pal.name) < 0:
                self.pal_combo.insertItem(self.pal_combo.count() - 1, pal.name)
            self.pal_combo.setCurrentText(pal.name)
        else:
            pal = Palette.load(self.palettes[name])
            self.settings.palette = name
        self.palette = pal
        self._rebuild_list()
        self.documentChanged.emit()

    # ================================================================ export
    def export_current(self) -> None:
        i = self.list.currentRow()
        if self.dc6 is None or i < 0:
            return
        fmt = self.settings.export_format
        start = Path(self.settings.last_dir("export", str(self.path.parent if self.path else "")))
        default = start / frame_filename(i, self.dc6.frame_count, EXPORT_FORMATS.get(fmt, ".bmp"))
        path, chosen = QFileDialog.getSaveFileName(
            self,
            f"Export frame {i:04d}",
            str(default),
            ";;".join(EXPORT_FILTERS.values()),
            EXPORT_FILTERS.get(fmt, ""),
        )
        if not path:
            return
        fmt = next((k for k, v in EXPORT_FILTERS.items() if v == chosen), fmt)
        path = Path(path)
        if path.suffix.lower() not in (*EXPORT_FORMATS.values(), ".tiff"):
            path = path.with_suffix(EXPORT_FORMATS[fmt])
        try:
            export_frame(self.dc6.frames[i].pixels, self.palette, path)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.settings.export_format = fmt
        self.settings.set_last_dir("export", str(path.parent))
        self.statusMessage.emit(f"Frame {i:04d} exported to {path}")

    def export_all(self) -> None:
        if self.dc6 is None:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Export all frames to folder", self.settings.last_dir("export_all")
        )
        if not folder:
            return
        formats = list(EXPORT_FORMATS)
        fmt, ok = QInputDialog.getItem(
            self,
            "File type",
            "Export all frames as:",
            formats,
            formats.index(self.settings.export_format) if self.settings.export_format in formats else 0,
            False,
        )
        if not ok:
            return
        ext = EXPORT_FORMATS[fmt]
        folder_p = Path(folder)
        indices = [i for i, f in enumerate(self.dc6.frames) if not f.blank]
        names = {i: frame_filename(i, self.dc6.frame_count, ext) for i in indices}
        existing = [n for n in names.values() if (folder_p / n).exists()]
        if (
            existing
            and QMessageBox.question(
                self,
                "Overwrite files?",
                f"{len(existing)} file(s) already exist in this folder (e.g. {existing[0]}). Overwrite them?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        progress = QProgressDialog("Exporting frames…", "Cancel", 0, len(indices), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        meta = []
        try:
            for n, i in enumerate(indices):
                if progress.wasCanceled():
                    break
                fr = self.dc6.frames[i]
                export_frame(fr.pixels, self.palette, folder_p / names[i])
                meta.append(
                    {
                        "index": i,
                        "file": names[i],
                        "width": fr.width,
                        "height": fr.height,
                        "offset_x": fr.offset_x,
                        "offset_y": fr.offset_y,
                    }
                )
                if n % 25 == 0:
                    progress.setValue(n)
            (folder_p / "frames.json").write_text(
                json.dumps(
                    {
                        "source": self.file_name,
                        "palette": self.palette.name,
                        "directions": self.dc6.directions,
                        "frames_per_dir": self.dc6.frames_per_dir,
                        "frames": meta,
                    },
                    indent=1,
                ),
                encoding="utf-8",
            )
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        finally:
            progress.close()
        self.settings.export_format = fmt
        self.settings.set_last_dir("export_all", folder)
        self.statusMessage.emit(f"{len(meta)} frame(s) exported to {folder_p} (+ frames.json)")

    # ================================================================ import
    def _target_size(self, i: int) -> tuple[int, int] | None:
        assert self.dc6 is not None
        fr = self.dc6.frames[i]
        return None if fr.blank else fr.size

    def import_current(self) -> None:
        i = self.list.currentRow()
        if self.dc6 is None or i < 0:
            return
        exts = " ".join(f"*{e}" for e in IMPORT_EXTENSIONS)
        path, _ = QFileDialog.getOpenFileName(
            self, f"Import image into frame {i:04d}", self.settings.last_dir("import"), f"Images ({exts})"
        )
        if not path:
            return
        path = Path(path)
        self.settings.set_last_dir("import", str(path.parent))
        res = check_image(path, self.palette, self._target_size(i), i)
        if not res.ok:
            ImportErrorDialog(path.name, res.errors, self).exec()
            return
        fr = self.dc6.frames[i]
        if res.warnings:
            dlg = ImportConfirmDialog(fr.pixels, res.indices, self.palette, path.name, i, res.warnings, self)
            if dlg.exec() != ImportConfirmDialog.DialogCode.Accepted:
                self.statusMessage.emit("Import aborted – nothing changed")
                return
        self._apply_import({i: res.indices})
        self.statusMessage.emit(f"Frame {i:04d} replaced by {path.name}")

    def import_all(self) -> None:
        if self.dc6 is None:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Import all frames from folder", self.settings.last_dir("import_all")
        )
        if not folder:
            return
        self.settings.set_last_dir("import_all", folder)
        files = sorted(p for p in Path(folder).iterdir() if p.is_file() and p.name != "frames.json")
        if not files:
            QMessageBox.information(self, "Import All", "The folder contains no files.")
            return
        by_index: dict[int, list[Path]] = {}
        rows: list[ReportRow] = []
        for p in files:
            idx = parse_frame_filename(p.name)
            if idx is None:
                rows.append(
                    ReportRow(
                        p.name,
                        "–",
                        "Skipped",
                        "Not a frame file (name must be the frame number, e.g. 0018.bmp / .pcx / "
                        ".png / .gif / .tif).",
                    )
                )
            else:
                by_index.setdefault(idx, []).append(p)

        last = self.dc6.frame_count - 1
        accepted: dict[int, np.ndarray] = {}
        progress = QProgressDialog("Checking files…", "Cancel", 0, len(by_index), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        for n, (idx, paths) in enumerate(sorted(by_index.items())):
            progress.setValue(n)
            if progress.wasCanceled():
                return
            if len(paths) > 1:
                names = ", ".join(p.name for p in paths)
                rows += [
                    ReportRow(
                        p.name,
                        f"{idx:04d}",
                        "Error",
                        f"Several files target frame {idx:04d} ({names}). Keep only one.",
                    )
                    for p in paths
                ]
                continue
            p = paths[0]
            if idx > last:
                rows.append(
                    ReportRow(
                        p.name,
                        f"{idx:04d}",
                        "Error",
                        f"Frame {idx:04d} does not exist (this DC6 has 0000–{last:04d}). "
                        "Add blank frames first.",
                    )
                )
                continue
            res = check_image(p, self.palette, self._target_size(idx), idx)
            if not res.ok:
                rows.append(ReportRow(p.name, f"{idx:04d}", "Error", " ".join(res.errors)))
            elif res.warnings:
                rows.append(ReportRow(p.name, f"{idx:04d}", "Warning", " ".join(res.warnings)))
                accepted[idx] = res.indices
            else:
                w, h = res.size or (0, 0)
                rows.append(ReportRow(p.name, f"{idx:04d}", "OK", f"{w}×{h}. " + " ".join(res.notes)))
                accepted[idx] = res.indices
        progress.close()

        dlg = ImportAllReportDialog(folder, rows, len(accepted), self)
        if dlg.exec() != ImportAllReportDialog.DialogCode.Accepted or not accepted:
            self.statusMessage.emit("Import All cancelled – nothing changed")
            return
        self._apply_import(accepted)
        self.statusMessage.emit(f"{len(accepted)} frame(s) replaced from {folder}")

    def _apply_import(self, new: dict[int, np.ndarray]) -> None:
        assert self.dc6 is not None
        std_before = self.dc6.standard_size()
        for i, px in new.items():
            self.dc6.frames[i].set_pixels(px)
        if self.dc6.standard_size() != std_before or len(new) > 50:
            self._rebuild_list()
        else:
            for i in new:
                self._refresh_item(i)
            self._show_frame(self.list.currentRow())
            self._update_file_info()
        self._set_modified(True)
        self.documentChanged.emit()

    # ================================================================ offsets
    def change_offsets(self) -> None:
        i = self.list.currentRow()
        if self.dc6 is None or i < 0:
            return
        fr = self.dc6.frames[i]
        dlg = OffsetDialog(i, fr.offset_x, fr.offset_y, self)
        if dlg.exec() != OffsetDialog.DialogCode.Accepted:
            return
        new = dlg.values()
        if new == (fr.offset_x, fr.offset_y):
            return
        fr.offset_x, fr.offset_y = new
        self._show_frame(i)
        self._set_modified(True)
        self.statusMessage.emit(f"Frame {i:04d}: offset changed to X {new[0]}, Y {new[1]}")

    # ================================================================ blank frames
    def add_blank_frame(self) -> None:
        if self.dc6 is None:
            return
        self.dc6.add_blank_frame()
        if self.dc6.directions == 1:
            self.list.addItem(self._make_item(self.dc6.frame_count - 1))
            self.list.setCurrentRow(self.dc6.frame_count - 1)
            self._update_file_info()
        else:
            self._rebuild_list()
        self.stateChanged.emit()
        self.statusMessage.emit(
            f"New frame {self.dc6.frames_per_dir - 1:04d} added (saved only once a graphic is imported)"
        )

    def remove_last_frame(self) -> None:
        if self.dc6 is None:
            return
        last = [
            self.dc6.frames[d * self.dc6.frames_per_dir + self.dc6.frames_per_dir - 1]
            for d in range(self.dc6.directions)
        ]
        if self.dc6.frames_per_dir <= 1:
            QMessageBox.information(self, "Remove last frame", "A DC6 needs at least one frame.")
            return
        real = not all(f.blank for f in last)
        if (
            real
            and QMessageBox.question(
                self,
                "Remove last frame",
                f"Frame {self.dc6.frames_per_dir - 1:04d} contains a graphic.<br>Remove it from the DC6? "
                "(The file changes when you save.)",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.dc6.remove_last_frame()
        if self.dc6.directions == 1:
            self.list.takeItem(self.list.count() - 1)
            self._update_file_info()
        else:
            self._rebuild_list()
        if real:
            self._set_modified(True)
            self.documentChanged.emit()
        else:
            self.stateChanged.emit()
        self.statusMessage.emit("Last frame removed")
