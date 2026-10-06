"""程序入口。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .ui.main_window import MainWindow


def _icon_path() -> Path:
    """定位图标：打包后在 _MEIPASS，开发时在项目根 assets/。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets" / "truffle.ico"
    return Path(__file__).resolve().parents[2] / "assets" / "truffle.ico"


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon = _icon_path()
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    if os.environ.get("TRUFFLE_SMOKE") == "1":
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1200, app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
