"""程序入口。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
