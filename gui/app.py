"""GUI entry point (started by main.py)."""

import sys

from core import APP_AUTHOR, APP_NAME, APP_VERSION
from core.paths import ICON_PATH
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication


def main() -> None:
    if sys.platform == "win32":  # own taskbar icon instead of the Python one
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"{APP_AUTHOR}.{APP_NAME}.{APP_VERSION}"
        )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_AUTHOR)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    app.setWindowIcon(QIcon(str(ICON_PATH)))

    from gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    files = [a for a in sys.argv[1:] if a.lower().endswith(".dc6")]
    if files:
        window.open_path(files[0])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
