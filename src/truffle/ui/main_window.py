"""主窗口：组织菜单、对话面板与图像画布，串联各层。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
)

from ..agent.llm_client import LLMClient
from ..agent.orchestrator import Orchestrator
from ..config import AppSettings
from ..core.image_doc import ImageDocument
from ..cv.analyzer import Analyzer
from ..tools.registry import build_default_registry
from .chat_panel import ChatPanel
from .image_view import ImageView
from .settings_dialog import SettingsDialog
from .worker import AgentWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Truffle · AI 修图")
        self.resize(1180, 760)

        self.settings = AppSettings.load()
        self.doc = ImageDocument()
        self.registry = build_default_registry()
        self.analyzer = Analyzer()
        self._worker: AgentWorker | None = None

        self.chat = ChatPanel()
        self.view = ImageView()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.chat)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 800])
        self.setCentralWidget(splitter)

        self._build_menu()
        self.statusBar().showMessage(
            "就绪" + ("" if self.settings.is_configured else " · 请先在「设置」中配置大模型 API")
        )
        self.chat.add_system(
            "你好，我是 Truffle ✨ 打开一张图片，然后用大白话告诉我想怎么修吧。"
        )

        QTimer.singleShot(300, self._first_run_setup)

    def _first_run_setup(self) -> None:
        """首次运行（未配置 API）时，自动弹出设置窗口，无需手动找菜单。"""
        if os.environ.get("TRUFFLE_SMOKE") == "1":
            return
        if self.settings.is_configured:
            return
        self.chat.add_system("首次使用：请先填写大模型配置，之后就能开始修图啦。")
        self._open_settings()

    # ---------- 菜单 ----------
    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        open_act = file_menu.addAction("打开图片…")
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_image)
        save_act = file_menu.addAction("另存为…")
        save_act.setShortcut("Ctrl+S")
        save_act.triggered.connect(self._save_image)
        file_menu.addSeparator()
        quit_act = file_menu.addAction("退出")
        quit_act.triggered.connect(self.close)

        edit_menu = self.menuBar().addMenu("编辑")
        undo_act = edit_menu.addAction("撤销")
        undo_act.setShortcut("Ctrl+Z")
        undo_act.triggered.connect(self._undo)
        redo_act = edit_menu.addAction("重做")
        redo_act.setShortcut("Ctrl+Y")
        redo_act.triggered.connect(self._redo)
        reset_act = edit_menu.addAction("恢复原图")
        reset_act.triggered.connect(self._reset)

        settings_menu = self.menuBar().addMenu("设置")
        cfg_act = settings_menu.addAction("大模型配置…")
        cfg_act.triggered.connect(self._open_settings)

        self.chat.submitted.connect(self._on_submit)

    # ---------- 文件 ----------
    def _open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开图片",
            "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)",
        )
        if not path:
            return
        try:
            self.doc.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "打开失败", str(exc))
            return
        self._refresh_view()
        self.chat.add_system(f"已打开：{Path(path).name}")

    def _save_image(self) -> None:
        if not self.doc.is_loaded:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", "truffle_output.png", "图片 (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        try:
            self.doc.save(path)
            self.chat.add_system(f"已保存到：{path}")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    # ---------- 编辑 ----------
    def _undo(self) -> None:
        if self.doc.undo():
            self._refresh_view()

    def _redo(self) -> None:
        if self.doc.redo():
            self._refresh_view()

    def _reset(self) -> None:
        if self.doc.is_loaded:
            self.doc.reset()
            self._refresh_view()

    def _refresh_view(self) -> None:
        if self.doc.is_loaded:
            self.view.set_array(self.doc.current)

    # ---------- 设置 ----------
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings.llm, self)
        if dialog.exec() == SettingsDialog.Accepted:
            self.settings.llm = dialog.result_settings()
            self.settings.save()
            if self.settings.is_configured:
                self.statusBar().showMessage("配置已保存，可以开始修图啦", 5000)
            else:
                self.statusBar().showMessage("已保存，但 API Key 为空", 5000)

    # ---------- 对话 ----------
    def _on_submit(self, text: str) -> None:
        if not self.settings.is_configured:
            self.chat.add_system("请先在「设置」里配置大模型 API Key。")
            self._open_settings()
            if not self.settings.is_configured:
                return
        if not self.doc.is_loaded:
            self.chat.add_system("请先打开一张图片。")
            return

        try:
            llm = LLMClient(self.settings.llm)
        except Exception as exc:
            self.chat.add_system(str(exc))
            return

        orchestrator = Orchestrator(self.doc, self.registry, llm, self.analyzer)
        self.chat.add_user(text)
        self.chat.set_busy(True)

        self._worker = AgentWorker(orchestrator, text)
        self._worker.imageReady.connect(self._refresh_view)
        self._worker.replied.connect(self.chat.add_assistant)
        self._worker.failed.connect(lambda msg: self.chat.add_system(f"出错了：{msg}"))
        self._worker.finished.connect(lambda: self.chat.set_busy(False))
        self._worker.start()
