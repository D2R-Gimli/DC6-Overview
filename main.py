"""DC6-Overview v1.0.0 by GimliHC: view, extract, import and overview Diablo II .dc6 files.

python main.py                       start the GUI
python main.py MaxiMap.dc6           start the GUI and open a file
python main.py overview MaxiMap.dc6  command line (also: validate, export-frames; add -h for help)
"""

import sys

CLI_COMMANDS = {"overview", "validate", "export-frames"}


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in CLI_COMMANDS:
        from core.cli import main as cli_main

        sys.exit(cli_main(sys.argv[1:]))
    from gui.app import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
