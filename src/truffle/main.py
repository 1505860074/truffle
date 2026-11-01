"""程序入口：配置/登录 → 项目页 → 主窗口。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .ui.app_controller import AppController


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

    request = sys.argv[1] if len(sys.argv) > 1 else None
    if os.environ.get("TRUFFLE_SMOKE") != "1" and os.environ.get("TRUFFLE_ALLOW_MULTI") != "1":
        if AppController.forward_to_existing(request):
            return

    controller = AppController(app)
    controller.start(request)
    if os.environ.get("TRUFFLE_SMOKE") == "1":
        QTimer.singleShot(1200, app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
