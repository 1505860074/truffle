"""程序入口。"""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    if os.environ.get("TRUFFLE_SMOKE") == "1":
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1200, app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
