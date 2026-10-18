"""Main window: DC6 Viewer + Overview tabs, menu, status bar, drag & drop."""

from pathlib import Path

from core import APP_NAME, APP_VERSION
from core.paths import ICON_PATH
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import QMainWindow, QTabWidget

from gui.dialogs import AboutDialog
from gui.overview_tab import OverviewTab
from gui.settings import Settings
from gui.viewer_tab import ViewerTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings()
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setAcceptDrops(True)

        self.viewer = ViewerTab(self.settings)
        self.overview = OverviewTab(self.settings)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.viewer, "DC6 Viewer")
        self.tabs.addTab(self.overview, "Overview")
        self.setCentralWidget(self.tabs)

        self.viewer.documentChanged.connect(self._push_to_overview)
        self.viewer.stateChanged.connect(self._update_title)
        self.viewer.statusMessage.connect(lambda m: self.statusBar().showMessage(m, 15000))
        self.overview.statusMessage.connect(lambda m: self.statusBar().showMessage(m, 15000))

        menu = self.menuBar().addMenu("&File")
        for text, key, slot in (
            ("&Open…", QKeySequence.StandardKey.Open, lambda: self.viewer.open_file()),
            ("&Save", QKeySequence.StandardKey.Save, self.viewer.save),
            ("Save &As…", QKeySequence.StandardKey.SaveAs, self.viewer.save_as),
        ):
            action = QAction(text, self)
            action.setShortcut(key)
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction("E&xit", self.close)
        self.menuBar().addMenu("&Help").addAction("&About", lambda: AboutDialog(self).exec())

        geometry = self.settings.geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1400, 880)
        self._update_title()
        self.statusBar().showMessage("Open a .dc6 file (File → Open, or drag & drop it onto the window)")

    def _update_title(self) -> None:
        name = (self.viewer.file_name + ("*" if self.viewer.modified else "")) if self.viewer.dc6 else ""
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}" + (f" – {name}" if name else ""))

    def _push_to_overview(self) -> None:
        folder = str(self.viewer.path.parent) if self.viewer.path else ""
        self.overview.set_source(
            self.viewer.overview_frames(), self.viewer.palette, self.viewer.file_name, folder
        )
        self._update_title()

    def open_path(self, path: str | Path) -> None:
        self.viewer.open_file(path)

    # drag & drop a .dc6 onto the window
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        urls = event.mimeData().urls()
        if urls and urls[0].toLocalFile().lower().endswith(".dc6"):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.tabs.setCurrentWidget(self.viewer)
        self.viewer.open_file(event.mimeData().urls()[0].toLocalFile())

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if not self.viewer.maybe_save():
            event.ignore()
            return
        self.settings.set_geometry(self.saveGeometry())
        event.accept()
