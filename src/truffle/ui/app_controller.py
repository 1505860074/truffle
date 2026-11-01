"""应用控制器：配置/登录 → 项目页 → 主窗口。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from ..config import AppSettings
from ..core.account import Account
from ..core.project import RecentProjects, migrate_session, open_project
from .account_dialog import AccountDialog
from .i18n import set_language, tr
from .project_page import ProjectPage
from .settings_dialog import SettingsDialog
from . import theme

IPC_NAME = "Truffle.IPC.v1"


class AppController(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.settings = AppSettings.load()
        self.ai_enabled = True
        self.page: ProjectPage | None = None
        self.window = None
        self._server: QLocalServer | None = None
        self._opening = False
        self._quitting = False

    # ---------- 启动 ----------
    def start(self, initial: str | None = None) -> None:
        theme.set_theme(self.settings.theme)
        set_language(self.settings.language)
        try:
            migrate_session(self.settings)
        except Exception:
            pass
        self._startup_dialogs()
        self.page = ProjectPage(self.settings)
        self.page.openRequested.connect(self.open_project)
        self.page.quitRequested.connect(self.quit)
        self._start_ipc()
        self.page.showMaximized()
        if initial:
            QTimer.singleShot(0, lambda: self.open_project(initial))

    def _startup_dialogs(self) -> None:
        if os.environ.get("TRUFFLE_SMOKE") == "1":
            return
        if not self.settings.is_configured:
            dialog = SettingsDialog(self.settings.llm)
            if dialog.exec() == SettingsDialog.Accepted:
                self.settings.llm = dialog.result_settings()
                self.settings.save()
            else:
                self.ai_enabled = False
        acc = Account(self.settings)
        if self.settings.require_login and acc.configured() and not acc.logged_in():
            dialog = AccountDialog()
            if dialog.exec() == AccountDialog.Accepted:
                mode, username, password = dialog.result_credentials()
                if username and password:
                    try:
                        result = (
                            acc.signup(username, password)
                            if mode == "register"
                            else acc.login(username, password)
                        )
                        acc.save_session(result)
                    except Exception:
                        self.ai_enabled = False
            else:
                self.ai_enabled = False

    # ---------- 项目 ----------
    def open_project(self, path: str) -> None:
        if self._opening:
            return
        target = Path(path)
        if not target.exists():
            QMessageBox.warning(self.page, tr("打开项目"), tr("项目文件不存在：") + "\n" + path)
            if self.page is not None:
                self.page.refresh()
            return
        self._opening = True
        try:
            if self.window is not None:
                self.window.close()
                self.window = None
            project = open_project(target)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self.page, tr("打开项目"), tr("无法打开项目：") + "\n" + str(exc))
            self._opening = False
            return
        RecentProjects().add(target, project.name)
        try:
            from .main_window import MainWindow

            ai_ok = bool(self.settings.is_configured)
            acc = Account(self.settings)
            if self.settings.require_login and acc.configured() and not acc.logged_in():
                ai_ok = False
            window = MainWindow(project=project, controller=self, ai_enabled=ai_ok)
            window.closed.connect(self._back_to_page)
            self.window = window
            if self.page is not None:
                self.page.hide()
            window.show()
        except Exception as exc:  # noqa: BLE001
            project.close()
            QMessageBox.critical(self.page, tr("打开项目"), tr("无法打开主窗口：") + "\n" + str(exc))
            self._opening = False
            return
        self._opening = False

    def _back_to_page(self) -> None:
        self.window = None
        if self.page is not None:
            self.page.refresh()
            self.page.showMaximized()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        if self.window is not None:
            self.window.close()
            self.window = None
        self.app.quit()

    # ---------- 单实例转发 ----------
    def _start_ipc(self) -> None:
        QLocalServer.removeServer(IPC_NAME)
        server = QLocalServer(self)
        server.newConnection.connect(self._on_ipc)
        if server.listen(IPC_NAME):
            self._server = server

    def _on_ipc(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            socket.readyRead.connect(lambda s=socket: self._read_ipc(s))
            socket.disconnected.connect(socket.deleteLater)

    def _read_ipc(self, socket: QLocalSocket) -> None:
        raw = bytes(socket.readAll()).decode("utf-8", "replace").strip()
        socket.disconnectFromServer()
        if raw:
            self.open_project(raw)
        elif self.page is not None:
            self.page.showMaximized()

    # ---------- 供 main.py 使用 ----------
    @staticmethod
    def forward_to_existing(path: str | None) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(IPC_NAME)
        if not socket.waitForConnected(350):
            return False
        socket.write((path or "").encode("utf-8"))
        socket.waitForBytesWritten(350)
        socket.disconnectFromServer()
        return True
