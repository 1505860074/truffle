"""主窗口：组织菜单、固定侧栏（对话/参数/文件库）、画布与历史树。

- 三侧栏固定在左/右/底，菜单栏右上角图标按钮平移动画显隐，不可拖动；
- 画布区内左侧为「历史树」（可显隐；右键可删除/修改某步参数）；
- 参数栏按模块分类、所见即所得（降采样预览 + 全分辨率导出）；
- 支持按住看原图、拖拽/粘贴入库、快捷键、布局记忆。
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QRect, QSize, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..agent.llm_client import LLMClient
from ..agent.orchestrator import Orchestrator
from ..agent.solver import ParamSolver
from ..agent.style import PROFILES, resolve_style
from ..config import AppSettings
from ..core.account import Account, AccountError
from ..core.exif import inject_exif_app1, read_exif_app1
from ..core import session
from ..core.image_doc import Step
from ..core.layer_doc import LayerDocument
from ..core.project import ImagePayload, Project, read_image_state
from ..core.layers import ensure_bgra
from ..core.style import profile as style_profile
from ..cv.analyzer import Analyzer, shared_analyzer
from ..cv.metrics import measure
from ..cv.warp import local_push
from ..tools.base import ToolContext
from ..tools.pipeline import render_pipeline
from ..tools.registry import build_default_registry
from . import theme
from .account_dialog import AccountDialog
from .animated_dock import AnimatedDock
from .batch_dialog import BatchDialog
from .canvas_tools import CanvasToolBar
from .chat_panel import ChatPanel
from .export_dialog import ExportDialog
from .file_library import FileLibrary
from .general_settings_dialog import GeneralSettingsDialog
from .history_panel import HistoryPanel
from .i18n import set_language, tr
from .image_view import ImageView
from .layers_panel import LayersPanel
from .naming import area_name
from .panel_icons import panel_icon
from .param_panel import ParamPanel
from .series_dialog import SeriesDialog
from .settings_dialog import SettingsDialog
from .step_edit_dialog import StepEditDialog
from .tool_labels import tool_label
from .updater import DownloadWorker, UpdateWorker
from .video_dialog import VideoDialog
from .worker import AgentWorker, BatchWorker, PreviewWorker, VideoWorker

IMAGE_FILTER = "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")
PREVIEW_MAX = 1400
HISTORY_WIDTH = 200
MAX_SIDE = 6000  # 载入图片最长边上限：超出则等比缩小，避免内存过大


class _LayoutView:
    def __init__(self, data: dict, fallback) -> None:
        self._data = data or {}
        self._fallback = fallback

    def __getattr__(self, name: str):
        if name in self._data:
            return self._data[name]
        return getattr(self._fallback, name)


class MainWindow(QMainWindow):
    closed = Signal()

    def __init__(self, project: Project | None = None, controller=None, ai_enabled: bool = True) -> None:
        super().__init__()
        self.project = project
        self.controller = controller
        self.ai_enabled = bool(ai_enabled)
        self._dirty = False
        self._pending_save = False
        self._image_docs: dict[str, LayerDocument] = {}
        self._image_selections: dict[str, np.ndarray | None] = {}
        self._image_params: dict[str, object] = {}
        self._image_views: dict[str, dict] = {}
        self._library_ids: dict[str, str] = {}
        self._autosave: QTimer | None = None
        self._agent_style = "natural"
        self._agent_orchestrator = None
        if project is not None:
            self.setWindowTitle(f"Truffle · {project.name} · v{__version__}")
        else:
            self.setWindowTitle(f"Truffle · AI 修图  v{__version__}")
        self.resize(1340, 840)
        self.setAcceptDrops(True)

        self.settings = AppSettings.load()
        theme.set_theme(self.settings.theme)
        set_language(self.settings.language)
        self.doc = LayerDocument()
        self.doc.set_renderer(self._render_step)
        self.registry = build_default_registry()
        self.analyzer = shared_analyzer()
        self._worker: AgentWorker | None = None
        self._preview_worker: PreviewWorker | None = None
        self._preview_image: np.ndarray | None = None
        self._pending_jobs: list | None = None
        self._jobs: list = []
        self._preview_base_img: np.ndarray | None = None
        self._preview_base_key = None
        self._preview_seq = 0
        self._mode = "view"
        self._force_quit = False
        self.conversation: list = []
        self.summary: str = ""

        self.chat = ChatPanel()
        self.view = ImageView()
        self.history = HistoryPanel()
        self.layers = LayersPanel()
        self.canvas_tools = CanvasToolBar()

        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(self.history)
        canvas = QWidget()
        canvas_lay = QVBoxLayout(canvas)
        canvas_lay.setContentsMargins(0, 0, 0, 0)
        canvas_lay.setSpacing(0)
        canvas_lay.addWidget(self.canvas_tools)
        canvas_lay.addWidget(self.view, 1)
        self.split.addWidget(canvas)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([HISTORY_WIDTH, 800])
        self.setCentralWidget(self.split)

        self._dock_titles: list[QWidget] = []
        self._chat_dock = AnimatedDock(area_name("chat"), horizontal=True)
        self._chat_dock.setWidget(self.chat)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._chat_dock)
        self._chat_dock.set_target(440)

        self.params = ParamPanel(self.registry)
        self._right_split = QSplitter(Qt.Vertical)
        self._right_split.addWidget(self.params)
        self._right_split.addWidget(self.layers)
        self._right_split.setStretchFactor(0, 1)
        self._right_split.setStretchFactor(1, 0)
        self._right_split.setSizes([520, 240])
        self._params_dock = AnimatedDock(area_name("params"), horizontal=True)
        self._params_dock.setWidget(self._right_split)
        self.addDockWidget(Qt.RightDockWidgetArea, self._params_dock)
        self._params_dock.set_target(400)

        self.library = FileLibrary()
        self._library_dock = AnimatedDock(area_name("files"), horizontal=False)
        self._library_dock.setWidget(self.library)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._library_dock)
        self._library_dock.set_target(200)

        for dock in (self._chat_dock, self._params_dock, self._library_dock):
            title = QWidget()
            dock.setTitleBarWidget(title)
            self._dock_titles.append(title)

        self._build_menu()
        self._build_shortcuts()
        self._restore_layout()

        self.statusBar().showMessage(
            tr("就绪") + ("" if self.settings.is_configured else tr(" · 请先在「设置」中配置大模型 API"))
        )
        if self.project is not None:
            self.summary = str(self.project.chat.get("summary", ""))
            messages = self.project.chat.get("messages", [])
            self.conversation = list(messages) if isinstance(messages, list) else []
        else:
            self.summary, self.conversation = session.load()
        if self.conversation:
            self._replay_conversation()
        else:
            self.chat.add_system(
                tr("你好，我是 Truffle ✨ 打开或拖入一张图片，然后在右侧拖动滑块，或直接告诉我想怎么修。")
            )
        self._refresh_history()
        self._refresh_layers()
        self._apply_theme(self.settings.theme)

        if self.project is not None:
            self._init_project()
        else:
            QTimer.singleShot(300, self._first_run_setup)
            QTimer.singleShot(600, self._enforce_login)
        QTimer.singleShot(4000, self._auto_check_update)
        if not self.ai_enabled:
            self.chat.input.setEnabled(False)
            self.chat.send_button.setEnabled(False)
            self.chat.add_system(tr("未配置大模型或未登录，AI 已禁用。请到「设置」或「账号」完成配置。"))

    # ---------- 历史树 ----------
    # ---------- 项目模式 ----------
    def _init_project(self) -> None:
        project = self.project
        if project is None:
            return
        self.library.path_mapper = self._map_project_path
        for entry in project.images:
            path = str(project.source_path(entry))
            if Path(path).exists():
                self.library.add_paths([path])
                self._library_ids[str(Path(path))] = entry.id
        if project.active_image_id:
            self._activate_image(project.active_image_id, initial=True)
        else:
            self.doc.clear()
            self._show_current()
        try:
            agent_path = project.workdir / "agent.json"
            if agent_path.exists():
                data = json.loads(agent_path.read_text(encoding="utf-8"))
                self._agent_style = str(data.get("style") or "natural")
        except Exception:
            pass
        interval = int(self.settings.autosave_interval or 0)
        if interval > 0:
            self._autosave = QTimer(self)
            self._autosave.setInterval(interval * 1000)
            self._autosave.timeout.connect(self._on_autosave)
            self._autosave.start()

    def _map_project_path(self, path: str) -> str:
        """文件库添加外部图片时，立即复制进项目并返回项目内路径。"""
        if self.project is None:
            return path
        source = Path(path)
        try:
            source.resolve().relative_to(self.project.workdir.resolve())
            return str(source)
        except Exception:
            pass
        try:
            entry = self.project.add_image(source)
            mapped = str(self.project.source_path(entry))
            self._library_ids[mapped] = entry.id
            self._mark_dirty()
            return mapped
        except Exception as exc:  # noqa: BLE001
            self.chat.add_system(tr("加入项目失败：") + str(exc))
            return path

    def _stash_current_image(self) -> None:
        if self.project is None or not self.doc.is_loaded:
            return
        image_id = self.project.active_image_id
        if not image_id:
            return
        self._image_docs[image_id] = self.doc
        try:
            self._image_selections[image_id] = self.view.selection()
        except Exception:
            pass
        try:
            self._image_params[image_id] = self.params.active_jobs()
        except Exception:
            pass

    def _activate_image(self, image_id: str, initial: bool = False) -> None:
        project = self.project
        if project is None:
            return
        entry = project.entry(image_id)
        if entry is None:
            return
        if not initial:
            self._stash_current_image()
        project.active_image_id = image_id
        project.touch_image(image_id)
        doc = self._image_docs.get(image_id)
        if doc is None:
            payload = None
            try:
                payload = read_image_state(project, entry)
            except Exception:
                payload = None
            if payload is not None:
                doc = payload.doc
                self._image_selections[image_id] = payload.selection
                if payload.params:
                    self._image_params[image_id] = payload.params
                if payload.view:
                    self._image_views[image_id] = payload.view
            else:
                doc = LayerDocument()
                source = str(project.source_path(entry))
                if not Path(source).exists():
                    self.chat.add_system(tr("项目内图片缺失：") + entry.display_name)
                    return
                doc.load(source)
            doc.set_renderer(self._render_step)
            doc.path = project.source_path(entry)
            self._image_docs[image_id] = doc
        self.doc = doc
        self.doc.set_renderer(self._render_step)
        self.view.set_array(self.doc.current)
        self.view.clear_selection()
        selection = self._image_selections.get(image_id)
        if selection is not None:
            self.view.set_selection(selection)
        self.params.reset_all()
        params = self._image_params.get(image_id) or []
        try:
            for name, values in params:
                group = self.params.groups.get(name)
                if group is not None:
                    group.set_values(values)
        except Exception:
            pass
        self.library.set_current(str(project.source_path(entry)))
        self.history.set_readonly(bool(getattr(self.doc, "history_readonly", False)))
        self._refresh_all()
        self._show_current()
        self._mark_dirty()
        self.statusBar().showMessage(tr("当前图片：") + entry.display_name)

    def _on_autosave(self) -> None:
        if self.project is None or not self._dirty:
            return
        if self._is_busy():
            self._pending_save = True
            return
        self._save_project()

    def _mark_dirty(self) -> None:
        if self.project is not None:
            self._dirty = True

    def _save_project(self, show_errors: bool = True) -> bool:
        project = self.project
        if project is None:
            return True
        self._stash_current_image()
        try:
            self._save_layout()
            loaded = {
                image_id: ImagePayload(
                    doc=doc,
                    selection=self._image_selections.get(image_id),
                    params=self._image_params.get(image_id),
                    view=self._image_views.get(image_id, {}),
                )
                for image_id, doc in self._image_docs.items()
            }
            cover_mode = str(project.cover.get("mode") or self.settings.default_cover_mode or "active")
            history_steps = int(project.history_steps if project.history_steps is not None else self.settings.history_steps)
            project.save(
                loaded,
                project.active_image_id,
                session._sanitize(self.conversation),
                self.summary,
                project.layout,
                history_steps,
                cover_mode,
            )
            self._dirty = False
            self._pending_save = False
            self.statusBar().showMessage(tr("已保存 ") + datetime.now().strftime("%H:%M:%S"), 5000)
            return True
        except Exception as exc:  # noqa: BLE001
            if show_errors:
                QMessageBox.critical(self, tr("保存项目失败"), str(exc))
            return False

    def _save_project_as(self) -> None:
        if self.project is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("项目另存为"), self.project.name + ".truffle", "Truffle 项目 (*.truffle)"
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".truffle":
            target = target.with_suffix(".truffle")
        if target.resolve() == self.project.path.resolve():
            self._save_project()
            return
        if target.exists():
            box = QMessageBox.question(self, tr("项目另存为"), tr("目标文件已存在，覆盖吗？"))
            if box != QMessageBox.Yes:
                return
        if not self._save_project():
            return
        try:
            shutil.copy2(self.project.path, target)
            self.project.path = target
            self.project.name = target.stem
            self.setWindowTitle(f"Truffle · {self.project.name} · v{__version__}")
            if self.controller is not None:
                from ..core.project import RecentProjects

                RecentProjects().add(target, self.project.name)
            self._save_project()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("项目另存为"), str(exc))

    def _apply_style_local(self, style_id: str) -> None:
        if not self.doc.is_loaded:
            self.chat.add_system(tr("请先打开一张图片。"))
            return
        profile = resolve_style(style_id)
        try:
            state = measure(self.doc.current, self.analyzer)
            solver = ParamSolver(self.registry, self.analyzer)
            result = solver.solve(self.doc.current, profile, state)
            executed = 0
            for name, params in result.jobs:
                source = self.doc.tool_source()
                new_image = self.registry.execute(name, source, ToolContext(self.analyzer), params)
                safe = self.registry.get(name).coerce_params(params)
                self.doc.commit_tool(name, safe, new_image, origin="ai")
                executed += 1
            if (
                executed > 1
                and self.settings.agent_history_mode == "request"
                and hasattr(self.doc, "collapse_recent")
            ):
                self.doc.collapse_recent(executed, "AI · " + profile.name, origin="ai")
            self._agent_style = profile.id
            self._agent_orchestrator = None
            if self.project is not None:
                try:
                    (self.project.workdir / "agent.json").write_text(
                        json.dumps(
                            {
                                "schema": 1,
                                "style": profile.id,
                                "state": measure(self.doc.current, self.analyzer, body=False),
                                "jobs": result.jobs,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            if executed:
                self._after_doc_change()
                self.chat.add_system(
                    tr("已应用风格：") + profile.name + f"（{executed} 步）"
                )
            else:
                self.chat.add_system(tr("当前图片已接近该风格，无需调整。"))
        except Exception as exc:  # noqa: BLE001
            self.chat.add_system(tr("应用风格失败：") + str(exc))

    def _project_settings(self) -> None:
        if self.project is None:
            return
        current = int(
            self.project.history_steps
            if self.project.history_steps is not None
            else self.settings.history_steps
        )
        value, ok = QInputDialog.getInt(
            self, tr("项目设置"), tr("历史步数（0~100）"), current, 0, 100, 1
        )
        if not ok:
            return
        self.project.history_steps = int(value)
        self._mark_dirty()
        self.statusBar().showMessage(tr("项目历史步数已设为 ") + str(value), 5000)

    def _reveal_project(self) -> None:
        if self.project is None:
            return
        try:
            subprocess.Popen(["explorer", "/select,", str(self.project.path.resolve())])
        except Exception:
            pass

    def _refresh_history(self) -> None:
        self.history.refresh(self.doc)

    def _refresh_all(self) -> None:
        self._refresh_history()
        self._refresh_layers()

    def _on_history_jump(self, pointer: int) -> None:
        self.doc.jump(pointer)
        self._after_doc_change()

    def _on_history_delete(self, index: int) -> None:
        self.doc.delete_step(index)
        self._after_doc_change()

    def _on_history_edit(self, index: int) -> None:
        step = self.doc.step_at(index)
        dialog = StepEditDialog(self.registry, step, self)
        if dialog.exec() == StepEditDialog.Accepted:
            data = dict(step.data)
            data.update(dialog.result_data())
            self.doc.update_step(index, data)
            self._after_doc_change()

    # ---------- 渲染步骤（非破坏式历史用） ----------
    def _render_step(self, image: np.ndarray, step: Step) -> np.ndarray:
        if step.kind == "tool":
            rendered = render_pipeline(
                self.registry, self.analyzer, image,
                [(step.data["name"], step.data["params"])],
            )
            mask = step.data.get("mask")
            if mask is not None and mask.shape[:2] == rendered.shape[:2]:
                alpha = (mask.astype(np.float32) / 255.0)[..., None]
                rendered = np.clip(
                    rendered.astype(np.float32) * alpha + image.astype(np.float32) * (1 - alpha),
                    0, 255,
                ).astype(np.uint8)
            return rendered
        if step.kind == "crop":
            x, y, w, h = step.data["rect"]
            H, W = image.shape[:2]
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(W, x + w), min(H, y + h)
            return np.ascontiguousarray(image[y0:y1, x0:x1])
        if step.kind == "liquify":
            img = image
            for stroke in step.data.get("strokes", []):
                img = local_push(img, *stroke)
            return img
        return image

    # ---------- 快捷键 ----------
    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+V"), self, self._paste_image)
        QShortcut(QKeySequence("Ctrl+R"), self, self._reset)

    # ---------- 首次运行 ----------
    def _first_run_setup(self) -> None:
        if os.environ.get("TRUFFLE_SMOKE") == "1":
            return
        if self.settings.is_configured:
            return
        self.chat.add_system(tr("首次使用：请先填写大模型配置，之后就能开始修图啦。"))
        self._open_settings()

    # ---------- 菜单 ----------
    def _view_action(self, menu, text: str, shortcut: str, slot):
        """菜单项 + 仅当画布获得焦点时生效的快捷键（避免抢占输入框）。"""
        act = menu.addAction(text)
        act.setShortcut(QKeySequence(shortcut))
        act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        act.triggered.connect(slot)
        self.view.addAction(act)
        return act

    def _build_menu(self) -> None:
        self.menuBar().setNativeMenuBar(False)

        corner = QWidget()
        self._menu_corner = corner
        lay = QHBoxLayout(corner)
        lay.setContentsMargins(0, 0, 10, 0)
        lay.setSpacing(4)
        brand = QLabel(area_name("menu"))
        self._brand = brand
        brand.setStyleSheet(
            f"color:{theme.current()['accent']}; font-size:12px; font-weight:bold; padding:0 6px;"
        )
        lay.addWidget(brand)
        self._panel_kinds = {"chat": "left", "params": "right", "files": "bottom"}
        self._panel_btns: dict[str, QToolButton] = {}
        for key, tip in (
            ("chat", "显示/隐藏对话栏"),
            ("params", "显示/隐藏参数栏"),
            ("files", "显示/隐藏文件库"),
        ):
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setIcon(panel_icon(self._panel_kinds[key], True))
            btn.setIconSize(QSize(18, 18))
            btn.setAutoRaise(True)
            btn.setToolTip(tip)
            btn.setStyleSheet(
                "QToolButton { border:none; padding:2px; border-radius:4px; } "
                "QToolButton:hover { background:#dcdcdc; }"
            )
            btn.clicked.connect(lambda checked, k=key: self._toggle_panel(k, checked))
            self._panel_btns[key] = btn
            lay.addWidget(btn)
        self.menuBar().setCornerWidget(corner, Qt.TopRightCorner)

        file_menu = self.menuBar().addMenu(tr("文件"))
        open_act = file_menu.addAction(tr("打开图片…"))
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_image)
        paste_act = file_menu.addAction(tr("粘贴图片"))
        paste_act.setShortcut("Ctrl+V")
        paste_act.triggered.connect(self._paste_image)
        save_act = file_menu.addAction(tr("导出图片…"))
        save_act.setShortcut("Ctrl+Shift+S")
        save_act.triggered.connect(self._save_image)
        batch_act = file_menu.addAction(tr("批量套用风格…"))
        batch_act.triggered.connect(self._batch_style)
        series_act = file_menu.addAction(tr("成套预览与导出…"))
        series_act.triggered.connect(self._series_preview)
        video_act = file_menu.addAction(tr("视频修饰…"))
        video_act.triggered.connect(self._video_retouch)
        file_menu.addSeparator()
        quit_act = file_menu.addAction(tr("退出"))
        quit_act.triggered.connect(self._quit_app)

        if self.project is not None:
            project_menu = self.menuBar().addMenu(tr("项目"))
            save_project = project_menu.addAction(tr("保存项目"))
            save_project.setShortcut("Ctrl+S")
            save_project.triggered.connect(lambda: self._save_project())
            save_as = project_menu.addAction(tr("项目另存为…"))
            save_as.triggered.connect(self._save_project_as)
            project_settings = project_menu.addAction(tr("项目设置…"))
            project_settings.triggered.connect(self._project_settings)
            project_menu.addSeparator()
            close_project = project_menu.addAction(tr("关闭项目"))
            close_project.triggered.connect(self.close)
            reveal = project_menu.addAction(tr("在资源管理器中显示"))
            reveal.triggered.connect(self._reveal_project)
            project_menu.addSeparator()
            quit_project = project_menu.addAction(tr("退出软件"))
            quit_project.triggered.connect(self._quit_app)

        edit_menu = self.menuBar().addMenu(tr("编辑"))
        undo_act = edit_menu.addAction(tr("撤销"))
        undo_act.setShortcut("Ctrl+Z")
        undo_act.triggered.connect(self._undo)
        redo_act = edit_menu.addAction(tr("重做"))
        redo_act.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        redo_act.triggered.connect(self._redo)
        reset_act = edit_menu.addAction(tr("恢复原图"))
        reset_act.setShortcut("Ctrl+R")
        reset_act.triggered.connect(self._reset)
        edit_menu.addSeparator()
        self._view_action(edit_menu, tr("自由变换"), "Ctrl+T",
                          lambda: self._on_tool_selected("transform"))
        edit_menu.addSeparator()
        clear_act = edit_menu.addAction(tr("清空对话"))
        clear_act.triggered.connect(self._clear_conversation)

        select_menu = self.menuBar().addMenu(tr("选择"))
        self._view_action(select_menu, tr("全选"), "Ctrl+A", self.view.select_all)
        self._view_action(select_menu, tr("取消选择"), "Ctrl+D", self.view.clear_selection)
        self._view_action(select_menu, tr("反选"), "Ctrl+Shift+I", self.view.invert_selection)

        layer_menu = self.menuBar().addMenu(tr("图层"))
        new_layer = layer_menu.addAction(tr("新建图层"))
        new_layer.setShortcut("Ctrl+Shift+N")
        new_layer.triggered.connect(self._add_layer)
        dup_layer = layer_menu.addAction(tr("复制图层"))
        dup_layer.setShortcut("Ctrl+J")
        dup_layer.triggered.connect(self._duplicate_layer)
        del_layer = layer_menu.addAction(tr("删除图层"))
        del_layer.triggered.connect(self._delete_layer)
        layer_menu.addSeparator()
        merge_down = layer_menu.addAction(tr("向下合并"))
        merge_down.setShortcut("Ctrl+E")
        merge_down.triggered.connect(self._merge_layer)
        merge_visible = layer_menu.addAction(tr("合并可见图层"))
        merge_visible.setShortcut("Ctrl+Shift+E")
        merge_visible.triggered.connect(self._flatten_layers)
        layer_menu.addSeparator()
        mask_act = layer_menu.addAction(tr("用选区创建蒙版"))
        mask_act.triggered.connect(self._add_layer_mask)
        del_mask = layer_menu.addAction(tr("删除蒙版"))
        del_mask.triggered.connect(self._delete_layer_mask)
        layer_menu.addSeparator()
        flip_h = layer_menu.addAction(tr("水平翻转图层"))
        flip_h.triggered.connect(lambda: self._flip_active_layer(True))
        flip_v = layer_menu.addAction(tr("垂直翻转图层"))
        flip_v.triggered.connect(lambda: self._flip_active_layer(False))

        view_menu = self.menuBar().addMenu(tr("视图"))
        self._view_action(view_menu, tr("放大"), "Ctrl++", self.view.zoom_in)
        self._view_action(view_menu, tr("缩小"), "Ctrl+-", self.view.zoom_out)
        self._view_action(view_menu, tr("适合窗口"), "Ctrl+0", self.view.fit_to_view)
        self._view_action(view_menu, tr("实际像素"), "Ctrl+1", self.view.actual_size)
        view_menu.addSeparator()
        for key in ("chat", "params", "files"):
            act = view_menu.addAction(area_name(key))
            act.setCheckable(True)
            act.setChecked(True)
            act.triggered.connect(lambda checked, k=key: self._toggle_panel(k, checked))
            self._panel_btns.setdefault("menu_" + key, act)

        style_menu = self.menuBar().addMenu(tr("风格"))
        for style_id, profile in PROFILES.items():
            action = style_menu.addAction(tr(profile.name))
            action.triggered.connect(lambda checked=False, sid=style_id: self._apply_style_local(sid))

        settings_menu = self.menuBar().addMenu(tr("设置"))
        general_act = settings_menu.addAction(tr("常规设置…"))
        general_act.triggered.connect(self._open_general_settings)
        cfg_act = settings_menu.addAction(tr("大模型配置…"))
        cfg_act.triggered.connect(self._open_settings)
        diag_act = settings_menu.addAction(tr("导出诊断信息…"))
        diag_act.triggered.connect(self._export_diagnostics)
        update_act = settings_menu.addAction(tr("检查更新…"))
        update_act.triggered.connect(self._check_update)

        account_menu = self.menuBar().addMenu(tr("账号"))
        login_act = account_menu.addAction(tr("登录 / 注册…"))
        login_act.triggered.connect(self._open_account)
        community_act = account_menu.addAction(tr("打开社区"))
        community_act.triggered.connect(self._open_community)

        self.chat.submitted.connect(self._on_submit)
        self.library.fileChosen.connect(self._open_from_library)
        self.library.deleteRequested.connect(self._on_library_delete)
        self.params.previewChanged.connect(self._on_preview)
        self.params.cropRequested.connect(self._enter_crop)
        self.params.liquifyRequested.connect(self._enter_liquify)
        self.params.selectRequested.connect(lambda: self._on_tool_selected("rect"))
        self.params.clearSelectionRequested.connect(self.view.clear_selection)
        self.view.selectionChanged.connect(self._on_selection_changed)
        self.params.modeApplyRequested.connect(lambda: self.view.apply_mode())
        self.params.modeCancelRequested.connect(lambda: self.view.cancel_mode())
        self.view.modeChanged.connect(self._on_mode_changed)
        self.view.cropApplied.connect(self._on_crop_applied)
        self.view.liquifyCommitted.connect(self._on_liquify_committed)
        self.view.toolRequested.connect(self._on_tool_selected)
        self.view.transformCommitted.connect(self._on_transform_committed)
        self.view.transformCancelled.connect(self._show_current)
        self.view.zoomChanged.connect(self.canvas_tools.set_zoom)
        self.view.nudgeRequested.connect(self._nudge_active)
        self.canvas_tools.toolSelected.connect(self._on_tool_selected)
        self.canvas_tools.applyRequested.connect(lambda: self.view.apply_mode())
        self.canvas_tools.cancelRequested.connect(lambda: self.view.cancel_mode())
        self.canvas_tools.featherChanged.connect(self.view.set_feather)
        self.canvas_tools.toleranceChanged.connect(self.view.set_tolerance)
        self.canvas_tools.contiguousChanged.connect(self.view.set_wand_contiguous)
        self.canvas_tools.selectionModeChanged.connect(self.view.set_selection_mode)
        self.canvas_tools.flipRequested.connect(self._flip_transform)
        self.layers.activeChanged.connect(self._on_layer_active)
        self.layers.visibilityChanged.connect(self._on_layer_visible)
        self.layers.opacityChanged.connect(self._on_layer_opacity)
        self.layers.opacityCommitted.connect(self._on_layer_opacity_done)
        self.layers.blendChanged.connect(self._on_layer_blend)
        self.layers.addRequested.connect(self._add_layer)
        self.layers.duplicateRequested.connect(self._duplicate_layer)
        self.layers.deleteRequested.connect(self._delete_layer)
        self.layers.mergeRequested.connect(self._merge_layer)
        self.layers.flattenRequested.connect(self._flatten_layers)
        self.layers.maskRequested.connect(self._add_layer_mask)
        self.layers.maskDeleteRequested.connect(self._delete_layer_mask)
        self.layers.moveRequested.connect(self._move_layer)
        self.layers.renameRequested.connect(self._rename_layer)
        self.history.jumpRequested.connect(self._on_history_jump)
        self.history.deleteRequested.connect(self._on_history_delete)
        self.history.editRequested.connect(self._on_history_edit)
        self.view.compareToggled.connect(self._on_compare)

    def _apply_theme(self, name: str) -> None:
        theme.set_theme(name)
        theme.apply_app_palette(QApplication.instance())
        t = theme.current()
        grad = (
            f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t['handle_end']}, "
            f"stop:0.5 {t['handle']}, stop:1 {t['handle_end']})"
        )
        self.setStyleSheet(
            f"QMainWindow::separator {{ width:1px; height:1px; background: {grad}; }}"
        )
        self.split.setStyleSheet(
            f"QSplitter::handle:horizontal {{ width:1px; background: {grad}; }}"
        )
        self._brand.setStyleSheet(
            f"color:{t['accent']}; font-size:12px; font-weight:bold; padding:0 6px;"
        )
        for widget in (self.chat, self.params, self.history, self.library, self.view,
                       self.layers, self.canvas_tools):
            if hasattr(widget, "apply_theme"):
                widget.apply_theme()
        for key, btn in self._panel_btns.items():
            if key in self._panel_kinds:
                btn.setIcon(panel_icon(self._panel_kinds[key], btn.isChecked()))

    def _toggle_panel(self, key: str, visible: bool) -> None:
        dock = {
            "chat": self._chat_dock,
            "params": self._params_dock,
            "files": self._library_dock,
        }[key]
        if visible:
            dock.slide_show()
        else:
            dock.slide_hide()
        btn = self._panel_btns.get(key)
        if btn is not None:
            btn.setChecked(visible)
            btn.setIcon(panel_icon(self._panel_kinds[key], visible))
        act = self._panel_btns.get("menu_" + key)
        if act is not None:
            act.setChecked(visible)

    # ---------- 布局记忆 ----------
    def _restore_layout(self) -> None:
        s = _LayoutView(self.project.layout, self.settings) if self.project is not None else self.settings
        self._chat_dock.set_target(s.chat_width)
        self._params_dock.set_target(s.params_width)
        self._library_dock.set_target(s.library_height)
        self.resizeDocks([self._chat_dock, self._params_dock], [s.chat_width, s.params_width], Qt.Horizontal)
        self.resizeDocks([self._library_dock], [s.library_height], Qt.Vertical)
        for key, dock, visible in (
            ("chat", self._chat_dock, s.chat_visible),
            ("params", self._params_dock, s.params_visible),
            ("files", self._library_dock, s.files_visible),
        ):
            dock.setVisible(visible)
            btn = self._panel_btns.get(key)
            if btn is not None:
                btn.setChecked(visible)
                btn.setIcon(panel_icon(self._panel_kinds[key], visible))
            act = self._panel_btns.get("menu_" + key)
            if act is not None:
                act.setChecked(visible)
        if s.window_geometry:
            try:
                self.restoreGeometry(base64.b64decode(s.window_geometry))
            except Exception:
                pass

    def _save_layout(self) -> None:
        data = {
            "chat_visible": self._chat_dock.isVisible(),
            "params_visible": self._params_dock.isVisible(),
            "files_visible": self._library_dock.isVisible(),
        }
        data["chat_width"] = self._chat_dock.current_size() if data["chat_visible"] else self._chat_dock.saved_size()
        data["params_width"] = self._params_dock.current_size() if data["params_visible"] else self._params_dock.saved_size()
        data["library_height"] = self._library_dock.current_size() if data["files_visible"] else self._library_dock.saved_size()
        try:
            data["window_geometry"] = base64.b64encode(bytes(self.saveGeometry())).decode()
        except Exception:
            pass
        if self.project is not None:
            self.project.layout.update(data)
            return
        for key, value in data.items():
            setattr(self.settings, key, value)
        self.settings.save()

    # ---------- 所见即所得预览 ----------
    def _on_preview(self, jobs) -> None:
        if self._mode not in ("view", "select"):
            return
        self._jobs = jobs
        if not jobs:
            self._preview_image = None
            self._pending_jobs = None
            self._show_current()
            self.params.set_status("")
            return
        self._pending_jobs = jobs
        if self._preview_worker is not None and self._preview_worker.isRunning():
            return
        self._start_preview(jobs)

    def _start_preview(self, jobs) -> None:
        self._pending_jobs = None
        self.params.set_status(tr("渲染中…"))
        self._preview_seq += 1
        token = self._preview_seq
        worker = PreviewWorker(
            self.registry, jobs, self._preview_base(), self.analyzer, self._current_mask()
        )
        worker.previewReady.connect(lambda img, tok=token: self._on_preview_ready(img, tok))
        worker.failed.connect(lambda _msg: self.params.set_status(""))
        worker.finished.connect(self._on_preview_finished)
        self._preview_worker = worker
        worker.start()

    def _preview_base(self) -> np.ndarray:
        cur = self.doc.current
        key = (id(cur), cur.shape)
        if self._preview_base_img is not None and self._preview_base_key == key:
            return self._preview_base_img
        h, w = cur.shape[:2]
        long_side = max(h, w)
        if long_side > PREVIEW_MAX:
            scale = PREVIEW_MAX / long_side
            small = cv2.resize(cur, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        else:
            small = cur.copy()
        self._preview_base_img = small
        self._preview_base_key = key
        return small

    def _current_mask(self) -> np.ndarray | None:
        return self.view.selection()

    def _on_selection_changed(self) -> None:
        self.params.set_selection_active(self._current_mask() is not None)
        if self._mode in ("view", "select") and self.params.active_jobs():
            self._on_preview(self.params.active_jobs())

    def _render_full(self) -> np.ndarray | None:
        jobs = self.params.active_jobs()
        if not jobs:
            return None
        rendered = render_pipeline(self.registry, self.analyzer, self.doc.current, jobs)
        mask = self._current_mask()
        if mask is not None and mask.shape[:2] == rendered.shape[:2]:
            alpha = (mask.astype(np.float32) / 255.0)[..., None]
            rendered = np.clip(
                rendered.astype(np.float32) * alpha + self.doc.current.astype(np.float32) * (1 - alpha),
                0, 255,
            ).astype(np.uint8)
        return rendered

    def _on_preview_ready(self, image: np.ndarray, token: int) -> None:
        # 丢弃过期结果（已有更新的请求在排队，或文档已变化）
        if token != self._preview_seq or self._pending_jobs is not None:
            return
        self._preview_image = image
        if self._mode == "view":
            self.view.set_array(image)
            self.params.set_status(tr("预览中"))

    def _on_preview_finished(self) -> None:
        if self._pending_jobs is not None:
            jobs = self._pending_jobs
            self._pending_jobs = None
            self._start_preview(jobs)

    def _commit_preview_silent(self) -> None:
        """把当前手动调节按步骤落进历史（每项工具一步）。"""
        jobs = self.params.active_jobs()
        if not jobs:
            return
        mask = self._current_mask()
        for name, params in jobs:
            data = {"name": name, "params": params}
            if mask is not None:
                data["mask"] = mask
            self.doc.push_op("tool", name, data, origin="manual")
        self._jobs = []
        self._preview_image = None
        self._pending_jobs = None
        self.params.reset_all()
        self._refresh_all()

    def _on_mode_changed(self, mode: str) -> None:
        self._mode = mode
        self.params.set_mode(mode)
        self.canvas_tools.set_mode(mode)
        self.view.compare.setEnabled(mode in ("view", "select"))
        if mode == "select":
            self.canvas_tools.set_selection_tool(self.view.selection_tool())
        self.params.set_status(
            {"crop": tr("裁剪中：拖拽选择区域后点「应用」"),
             "liquify": tr("液化中：拖动推挤像素后点「应用」"),
             "select": tr("选区中：拖拽创建选区，Shift 加选 / Alt 减选"),
             "transform": tr("自由变换中：拖拽控制点，Enter 应用 / Esc 取消"),
             "hand": tr("抓手：拖动平移画布"),
             "zoom": tr("缩放：单击放大，Alt+单击缩小")}.get(mode, ""))

    def _enter_crop(self) -> None:
        if not self.doc.is_loaded:
            self.chat.add_system(tr("请先打开一张图片。"))
            return
        self._commit_preview_silent()
        self.view.start_crop()

    def _enter_liquify(self, radius: float, strength: float) -> None:
        if not self.doc.is_loaded:
            self.chat.add_system(tr("请先打开一张图片。"))
            return
        self._commit_preview_silent()
        self.view.start_liquify(radius, strength)

    def _on_crop_applied(self, x: int, y: int, w: int, h: int) -> None:
        if not self.doc.is_loaded or w < 2 or h < 2:
            return
        img = self.doc.current
        H, W = img.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return
        self.doc.push_op("crop", "裁剪", {"rect": (x0, y0, x1 - x0, y1 - y0)}, origin="manual")
        self.params.reset_all()
        self._show_current()
        self._refresh_all()
        self.chat.add_system(tr("已裁剪为 ") + f"{x1 - x0}×{y1 - y0}")

    def _on_liquify_committed(self) -> None:
        strokes = self.view.strokes()
        if strokes:
            data = {"strokes": strokes, "layer": self.doc.active_layer.id if self.doc.active_layer else None}
            self.doc.push_op("liquify", "液化", data, origin="manual")
            self.params.reset_all()
            self._show_current()
            self._refresh_history()
            self._refresh_layers()
            self.chat.add_system(tr("液化已应用"))

    # ---------- 工具 / 选区 / 变换 ----------
    def _on_tool_selected(self, name: str) -> None:
        if not self.doc.is_loaded:
            self.chat.add_system(tr("请先打开一张图片。"))
            return
        if name in ("rect", "ellipse", "lasso", "polygon", "wand"):
            self._commit_preview_silent()
            self.view.set_feather(self.canvas_tools.feather_value())
            self.view.set_selection_mode(self.canvas_tools.selection_mode())
            self.view.start_select(name)
            self.canvas_tools.set_selection_tool(name)
        elif name == "crop":
            self._enter_crop()
        elif name == "liquify":
            radius = self.params.liquify.size.value() if hasattr(self.params, "liquify") else 80
            strength = self.params.liquify.strength.value() if hasattr(self.params, "liquify") else 0.5
            self._enter_liquify(float(radius), float(strength))
        elif name in ("transform", "move"):
            self._enter_transform()
        elif name in ("hand", "zoom"):
            self.view.set_tool_mode(name)
        self.view.setFocus()

    def _enter_transform(self) -> None:
        if not self.doc.is_loaded:
            return
        self.view.compare.setChecked(False)
        self._commit_preview_silent()
        layer = self.doc.active_layer
        if layer is None:
            return
        img = layer.image
        H, W = img.shape[:2]
        mask = self.view.selection()
        bbox = self.view.selection_bbox() if mask is not None else None
        if mask is not None and bbox is None:
            mask = None
        if mask is not None and bbox is not None:
            x, y, w, h = bbox
            x = max(0, min(x, W - 1))
            y = max(0, min(y, H - 1))
            w = max(1, min(w, W - x))
            h = max(1, min(h, H - y))
            patch = img[y:y + h, x:x + w].copy()
            m = mask[y:y + h, x:x + w].astype(np.float32) / 255.0
            patch[..., 3] = np.clip(patch[..., 3].astype(np.float32) * m, 0, 255).astype(np.uint8)
            base = img.copy()
            mfull = mask.astype(np.float32) / 255.0
            base[..., 3] = np.clip(
                base[..., 3].astype(np.float32) * (1.0 - mfull), 0, 255
            ).astype(np.uint8)
            self.chat.add_system(tr("自由变换选区：拖拽控制点，Enter 应用，Esc 取消。"))
        else:
            x, y, w, h = 0, 0, W, H
            patch = img.copy()
            base = img.copy()
            base[..., 3] = 0
            self.chat.add_system(tr("自由变换图层：拖拽控制点，Enter 应用，Esc 取消。"))
        base_full = self.doc.composite_with_active(base)
        self.view.start_transform((x, y, w, h), patch, base_full)
        self.canvas_tools.set_mode("transform")

    def _on_transform_committed(self, src_rect, dst_quad) -> None:
        mask = self.view.selection()
        self.doc.transform_active(src_rect, dst_quad, mask)
        self._after_doc_change()

    def _flip_transform(self, horizontal: bool) -> None:
        self.view.flip_transform(horizontal, not horizontal)

    def _flip_active_layer(self, horizontal: bool) -> None:
        if not self.doc.is_loaded:
            return
        self.doc.flip_active(horizontal, not horizontal)
        self._show_current()
        self._refresh_history()
        self._refresh_layers()

    def _nudge_active(self, dx: int, dy: int) -> None:
        if not self.doc.is_loaded:
            return
        self._commit_preview_silent()
        self.doc.translate_active(dx, dy)
        self._show_current()
        self._refresh_history()
        self._refresh_layers()

    # ---------- 图层 ----------
    def _refresh_layers(self) -> None:
        self.layers.refresh(self.doc)
        layer = self.doc.active_layer
        self.layers.set_mask_enabled(bool(layer and layer.mask is not None))

    def _on_layer_active(self, index: int) -> None:
        self.doc.set_active_layer(index)
        layer = self.doc.active_layer
        if layer is not None:
            self.statusBar().showMessage(tr("当前图层：") + layer.name, 2000)

    def _on_layer_visible(self, index: int, visible: bool) -> None:
        self.doc.set_layer_visible(index, visible)
        self._show_current()
        self._refresh_history()

    def _on_layer_opacity(self, value: int) -> None:
        if not self.doc.is_loaded:
            return
        self.doc.set_layer_opacity(self.doc.active_index, value / 100.0, record=False)
        self._show_current()

    def _on_layer_opacity_done(self) -> None:
        self.doc.record(tr("调整不透明度"))
        self._refresh_history()

    def _on_layer_blend(self, blend: str) -> None:
        if not self.doc.is_loaded:
            return
        self.doc.set_layer_blend(self.doc.active_index, blend)
        self._show_current()
        self._refresh_history()

    def _add_layer(self) -> None:
        if not self.doc.is_loaded:
            return
        self.doc.add_layer()
        self._after_doc_change()
        self.chat.add_system(tr("已新建图层。"))

    def _duplicate_layer(self) -> None:
        if not self.doc.is_loaded:
            return
        mask = self.view.selection()
        if mask is not None:
            self.doc.layer_via_copy(mask)
            self._after_doc_change()
            self.chat.add_system(tr("已通过拷贝选区新建图层。"))
        else:
            self.doc.duplicate_active_layer()
            self._after_doc_change()
            self.chat.add_system(tr("已复制当前图层。"))

    def _delete_layer(self) -> None:
        if not self.doc.is_loaded:
            return
        if len(self.doc.layers()) <= 1:
            self.chat.add_system(tr("至少保留一个图层。"))
            return
        self.doc.delete_active_layer()
        self._after_doc_change()
        self.chat.add_system(tr("已删除当前图层。"))

    def _merge_layer(self) -> None:
        if not self.doc.is_loaded or self.doc.active_index <= 0:
            self.chat.add_system(tr("当前图层下方没有可合并的图层。"))
            return
        self.doc.merge_down()
        self._after_doc_change()
        self.chat.add_system(tr("已向下合并图层。"))

    def _flatten_layers(self) -> None:
        if not self.doc.is_loaded:
            return
        self.doc.flatten_layers()
        self._after_doc_change()
        self.chat.add_system(tr("已合并可见图层。"))

    def _add_layer_mask(self) -> None:
        if not self.doc.is_loaded:
            return
        mask = self.view.selection()
        if mask is None:
            self.chat.add_system(tr("请先用选区工具框出要保留的区域，再创建蒙版。"))
            return
        self.doc.add_mask_from_selection(mask)
        self._show_current()
        self._refresh_history()
        self._refresh_layers()
        self.chat.add_system(tr("已用当前选区创建图层蒙版。"))

    def _delete_layer_mask(self) -> None:
        if not self.doc.is_loaded:
            return
        layer = self.doc.active_layer
        if layer is None or layer.mask is None:
            self.chat.add_system(tr("当前图层没有蒙版。"))
            return
        self.doc.delete_mask()
        self._show_current()
        self._refresh_history()
        self._refresh_layers()

    def _move_layer(self, delta: int) -> None:
        if not self.doc.is_loaded:
            return
        self.doc.move_active_layer(delta)
        self._after_doc_change()

    def _rename_layer(self, index: int, name: str) -> None:
        if not self.doc.is_loaded:
            return
        self.doc.rename_layer(index, name)
        self._refresh_layers()

    # ---------- 文件 ----------
    def _open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("打开图片"), "", IMAGE_FILTER)
        if not path:
            return
        if self.project is not None:
            entry = self.project.add_image(path)
            source = str(self.project.source_path(entry))
            self.library.add_paths([source])
            self._library_ids[str(Path(source))] = entry.id
            self._activate_image(entry.id)
            self._mark_dirty()
            return
        self.library.add_paths([path])
        self.library.set_current(path)
        self._open_from_library(path)

    def _open_from_library(self, path: str) -> None:
        if self.project is not None:
            image_id = self._library_ids.get(str(Path(path)))
            if image_id:
                self._activate_image(image_id)
            return
        if self.doc.is_loaded and self.doc.path is not None and str(self.doc.path) == str(Path(path)):
            return
        try:
            self.doc.load(path)
        except Exception as exc:
            self.chat.add_system(tr("无法打开 ") + f"{Path(path).name}：{exc}")
            return
        self._enforce_size_limit()
        self.library.set_current(path)
        self._after_doc_change()
        self.view.setFocus()
        self.chat.add_system(tr("已打开：") + Path(path).name)

    def _enforce_size_limit(self) -> None:
        """超大图自动等比缩小，避免内存过大导致卡顿/崩溃。"""
        img = self.doc.original
        h, w = img.shape[:2]
        long_side = max(h, w)
        if long_side <= MAX_SIDE:
            return
        scale = MAX_SIDE / long_side
        resized = cv2.resize(
            img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA
        )
        self.doc.set_original(resized)
        self.chat.add_system(
            tr("图片过大，已缩小到 ") + f"{resized.shape[1]}×{resized.shape[0]}" + tr(" 以便流畅编辑。")
        )

    def _export_diagnostics(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("导出诊断信息"), "truffle_diagnostics.txt", "文本 (*.txt)"
        )
        if not path:
            return
        lines = [
            f"Truffle v{__version__}",
            f"time: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"python: {sys.version}",
            f"frozen: {getattr(sys, 'frozen', False)}",
            f"theme={self.settings.theme} language={self.settings.language}",
            f"base_url={self.settings.llm.base_url}",
            f"model={self.settings.llm.model} timeout={self.settings.llm.timeout}",
            f"api_key_set={bool(self.settings.llm.api_key)}",
        ]
        log = Path(os.environ.get("APPDATA") or Path.home()) / "Truffle" / "error.log"
        if log.exists():
            lines.append("")
            lines.append("===== error.log =====")
            try:
                lines.append(log.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            self.chat.add_system(tr("诊断信息已导出到：") + str(path))
        except OSError as exc:
            QMessageBox.critical(self, tr("导出失败"), str(exc))

    def _paste_image(self) -> None:
        image = QApplication.clipboard().image()
        if image.isNull():
            self.chat.add_system(tr("剪贴板里没有图片。"))
            return
        qimg = image.convertToFormat(QImage.Format_RGB888)
        w, h = qimg.width(), qimg.height()
        ptr = qimg.constBits()
        arr = np.frombuffer(ptr, np.uint8).reshape(h, qimg.bytesPerLine())[:, : w * 3].reshape(h, w, 3)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        if self.doc.is_loaded:
            pasted = ensure_bgra(bgr)
            H, W = self.doc.current.shape[:2]
            ph, pw = pasted.shape[:2]
            if pw > W or ph > H:
                scale = min(W / pw, H / ph)
                pasted = cv2.resize(
                    pasted, (max(1, int(pw * scale)), max(1, int(ph * scale))),
                    interpolation=cv2.INTER_AREA,
                )
                ph, pw = pasted.shape[:2]
            canvas = np.zeros((H, W, 4), dtype=np.uint8)
            x, y = (W - pw) // 2, (H - ph) // 2
            canvas[y:y + ph, x:x + pw] = pasted
            self.doc.add_layer(tr("粘贴的图层"), image=canvas)
            self._after_doc_change()
            self.chat.add_system(tr("已粘贴为当前文档的新图层。"))
            return
        tmp = Path(tempfile.gettempdir()) / f"truffle_paste_{int(time.time() * 1000)}.png"
        cv2.imencode(".png", bgr)[1].tofile(str(tmp))
        if self.project is not None:
            entry = self.project.add_image(tmp)
            source = str(self.project.source_path(entry))
            self.library.add_paths([source])
            self._library_ids[str(Path(source))] = entry.id
            self._activate_image(entry.id)
            self._mark_dirty()
            try:
                tmp.unlink()
            except OSError:
                pass
            return
        self.library.add_paths([str(tmp)])
        self.library.set_current(str(tmp))
        self._open_from_library(str(tmp))
        self.chat.add_system(tr("已粘贴剪贴板图片并加入文件库。"))

    def _save_image(self) -> None:
        if not self.doc.is_loaded:
            return
        dialog = ExportDialog("truffle_output.png", self)
        if dialog.exec() != ExportDialog.Accepted:
            return
        path = dialog.result_path()
        quality = dialog.result_quality()
        keep_exif = dialog.result_keep_exif()
        image = self._render_full()
        if image is None:
            image = self.doc.current
        ext = Path(path).suffix.lower()
        params: list[int] = []
        if ext in (".jpg", ".jpeg"):
            params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        elif ext == ".webp":
            params = [cv2.IMWRITE_WEBP_QUALITY, quality]
        try:
            ok, buf = cv2.imencode(ext or ".png", image, params)
            if not ok:
                raise ValueError("无法编码图像")
            data = buf.tobytes()
            if keep_exif and ext in (".jpg", ".jpeg") and self.doc.path is not None:
                app1 = read_exif_app1(self.doc.path)
                if app1:
                    data = inject_exif_app1(data, app1)
            Path(path).write_bytes(data)
            self.doc.path = Path(path)
            self.chat.add_system(tr("已保存到：") + path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("保存失败"), str(exc))

    # ---------- 批量处理（套模板 / 自动调色） ----------
    def _series_preview(self) -> None:
        paths = self.library.paths()
        if not paths:
            self.chat.add_system(tr("文件库里没有图片。"))
            return
        dialog = SeriesDialog(paths, self.registry, self.analyzer, self._agent_style, self)
        dialog.exec()

    def _batch_style(self) -> None:
        library = self.library.paths()
        current = str(self.doc.path) if self.doc.path is not None else None
        name = Path(self.doc.path).name if self.doc.path else tr("当前图")
        dialog = BatchDialog(name, len(library), self)
        if dialog.exec() != BatchDialog.Accepted:
            return
        mode = dialog.result_mode()
        out_dir = dialog.result_out_dir()
        if not out_dir:
            self.chat.add_system(tr("请选择导出文件夹。"))
            return
        if mode == "auto":
            targets = list(library)
            template_profile = None
            if not targets:
                self.chat.add_system(tr("文件库里没有图片。"))
                return
        else:
            if not self.doc.is_loaded:
                self.chat.add_system(tr("请先打开一张作为模板的图片。"))
                return
            targets = [p for p in library if p != current]
            if not targets:
                self.chat.add_system(tr("文件库里没有其它图片可供批量套用。"))
                return
            template_profile = style_profile(self.doc.current)
        self._batch_worker = BatchWorker(
            self.registry, self.analyzer, template_profile, targets,
            out_dir, dialog.result_format(), dialog.result_quality(), mode,
        )
        self._batch_worker.progress.connect(
            lambda done, total, path: self.statusBar().showMessage(f"{done}/{total} · {Path(path).name}")
        )
        self._batch_worker.failed.connect(
            lambda msg: self.chat.add_system(tr("批量处理失败：") + msg)
        )
        self._batch_worker.finished_ok.connect(
            lambda n: self.chat.add_system(tr("批量完成：") + f"{n}" + tr(" 张。"))
        )
        self._batch_worker.start()
        self.chat.add_system(tr("开始批量套用风格…"))

    # ---------- 视频修饰 ----------
    def _video_retouch(self) -> None:
        dialog = VideoDialog(self.registry, self)
        if dialog.exec() != VideoDialog.Accepted:
            return
        inp = dialog.result_input()
        out = dialog.result_output()
        if not inp or not out:
            self.chat.add_system(tr("请选择输入与输出视频。"))
            return
        self._video_worker = VideoWorker(
            inp, out, self.registry, self.analyzer, dialog.result_jobs(), dialog.result_max_side()
        )
        self._video_worker.progress.connect(
            lambda done, total: self.statusBar().showMessage(tr("视频处理中 ") + f"{done}/{total}")
        )
        self._video_worker.failed.connect(
            lambda msg: self.chat.add_system(tr("视频处理失败：") + msg)
        )
        self._video_worker.finished_ok.connect(
            lambda path: self.chat.add_system(tr("视频已导出：") + path)
        )
        self._video_worker.start()
        self.chat.add_system(tr("开始处理视频…（不含音轨）"))

    # ---------- 拖拽 ----------
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile().lower().endswith(IMAGE_EXTS)
        ]
        if not paths:
            return
        self.library.add_paths(paths)
        origin = self.view.mapTo(self, self.view.rect().topLeft())
        over_canvas = QRect(origin, self.view.size()).contains(event.position().toPoint())
        if over_canvas:
            self.library.set_current(paths[0])
            self._open_from_library(paths[0])
        else:
            self.chat.add_system(tr("已加入文件库：") + f"{len(paths)}" + tr(" 张。"))
        event.acceptProposedAction()

    # ---------- 编辑 ----------
    def _undo(self) -> None:
        if self.doc.undo():
            self._after_doc_change()

    def _redo(self) -> None:
        if self.doc.redo():
            self._after_doc_change()

    def _reset(self) -> None:
        if self.doc.is_loaded:
            self.doc.reset()
            self._after_doc_change()

    def _after_doc_change(self) -> None:
        self._preview_seq += 1  # 使在途预览结果失效
        self._preview_image = None
        self._pending_jobs = None
        self._jobs = []
        self._preview_base_img = None
        self._preview_base_key = None
        self.params.reset_all()
        self.view.compare.setChecked(False)
        if self.view.mode() != "view":
            self.view.cancel_mode()
        self.view.clear_selection()
        self._show_current()
        self._refresh_all()
        self._mark_dirty()

    def _show_current(self) -> None:
        if not self.doc.is_loaded:
            self.view.clear()
            return
        if self._preview_image is not None and self._mode in ("view", "select"):
            self.view.set_array(self._preview_image)
        else:
            self.view.set_array(self.doc.current)

    def _on_library_delete(self, paths) -> None:
        paths = [str(Path(p)) for p in paths]
        if not paths:
            return
        if self.project is not None:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle(tr("从项目删除图片"))
            box.setText(tr("将同时删除项目内的图片副本、图层和历史。确定删除吗？"))
            yes = box.addButton(tr("删除"), QMessageBox.DestructiveRole)
            box.addButton(tr("取消"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not yes:
                return
            current = self.project.active_image_id
            for path in paths:
                image_id = self._library_ids.pop(str(Path(path)), None)
                if not image_id:
                    continue
                if image_id == current:
                    self.doc.clear()
                    self._show_current()
                self.project.remove_image(image_id)
                self._image_docs.pop(image_id, None)
                self._image_selections.pop(image_id, None)
                self._image_params.pop(image_id, None)
                self._image_views.pop(image_id, None)
            self.library.remove_paths(paths)
            self._mark_dirty()
            self._refresh_all()
            self._show_current()
            return
        current = str(self.doc.path) if (self.doc.is_loaded and self.doc.path is not None) else None
        if current is not None and current in set(paths):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle(tr("删除正在编辑的图片"))
            box.setText(tr("这张图片正在画布中编辑。\n删除后将从文件库移除，并清空画布。确定删除吗？"))
            yes = box.addButton(tr("删除"), QMessageBox.DestructiveRole)
            box.addButton(tr("取消"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not yes:
                return
            self.library.remove_paths(paths)
            self.doc.clear()
            self._after_doc_change()
            self.chat.add_system(tr("已从文件库删除，并清空画布。"))
        else:
            self.library.remove_paths(paths)
            self.chat.add_system(tr("已从文件库删除 ") + f"{len(paths)}" + tr(" 张。"))

    def _on_compare(self, on: bool) -> None:
        if not self.doc.is_loaded:
            self.view.compare.setChecked(False)
            return
        if on:
            self.view.set_array(self.doc.original)
        else:
            self._show_current()

    # ---------- 设置 ----------
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings.llm, self)
        if dialog.exec() == SettingsDialog.Accepted:
            self.settings.llm = dialog.result_settings()
            self.settings.save()
            if self.settings.is_configured:
                self.ai_enabled = True
                self.chat.input.setEnabled(True)
                self.chat.send_button.setEnabled(True)
            if self.settings.is_configured:
                self.statusBar().showMessage(tr("配置已保存，可以开始修图啦"), 5000)
            else:
                self.statusBar().showMessage(tr("已保存，但 API Key 为空"), 5000)

    def _open_general_settings(self) -> None:
        dialog = GeneralSettingsDialog(self.settings, self)
        if dialog.exec() != GeneralSettingsDialog.Accepted:
            return
        old_theme = self.settings.theme
        old_lang = self.settings.language
        old_assoc = self.settings.file_assoc
        old_project_assoc = self.settings.project_assoc
        self.settings.close_behavior = dialog.result_behavior()
        self.settings.project_dir = dialog.result_project_dir()
        self.settings.autosave_interval = dialog.result_autosave()
        self.settings.history_steps = dialog.result_history_steps()
        self.settings.agent_history_mode = dialog.result_agent_history()
        self.settings.project_view = dialog.result_project_view()
        self.settings.default_cover_mode = dialog.result_cover_mode()
        self.settings.project_assoc = dialog.result_project_assoc()
        self.settings.theme = dialog.result_theme()
        self.settings.language = dialog.result_language()
        self.settings.update_url = dialog.result_update_url()
        self.settings.auto_check_update = dialog.result_auto_check()
        self.settings.file_assoc = dialog.result_file_assoc()
        (
            self.settings.lc_app_id,
            self.settings.lc_app_key,
            self.settings.lc_server_url,
        ) = dialog.result_leancloud()
        self.settings.require_login = dialog.result_require_login()
        self.settings.community_url = dialog.result_community_url()
        self.settings.save()
        if self.project is not None and self._autosave is not None:
            interval = int(self.settings.autosave_interval or 0)
            if interval > 0:
                self._autosave.setInterval(interval * 1000)
                self._autosave.start()
            else:
                self._autosave.stop()
        if self.settings.theme != old_theme:
            self._apply_theme(self.settings.theme)
        if self.settings.file_assoc != old_assoc or self.settings.project_assoc != old_project_assoc:
            try:
                from ..core.shell import set_file_association, set_project_association

                set_file_association(self.settings.file_assoc)
                set_project_association(self.settings.project_assoc)
            except Exception as exc:  # noqa: BLE001
                self.chat.add_system(tr("设置文件关联失败：") + str(exc))
        if self.settings.language != old_lang:
            self.statusBar().showMessage(tr("语言将在重启后生效"), 5000)
        else:
            self.statusBar().showMessage(tr("常规设置已保存"), 3000)

    # ---------- 自动更新 ----------
    def _auto_check_update(self) -> None:
        if os.environ.get("TRUFFLE_SMOKE") == "1" or not self.settings.auto_check_update:
            return
        url = self.settings.update_url.strip()
        if not url:
            return
        self._update_worker = UpdateWorker(url, __version__)
        self._update_worker.found.connect(self._on_update_result)
        self._update_worker.failed.connect(lambda _msg: None)
        self._update_worker.start()

    def _check_update(self) -> None:
        url = self.settings.update_url.strip()
        if not url:
            self.chat.add_system(tr("未配置更新地址（可在「设置 → 常规设置」中填写）。"))
            return
        self.statusBar().showMessage(tr("正在检查更新…"))
        self._update_worker = UpdateWorker(url, __version__)
        self._update_worker.found.connect(self._on_update_result)
        self._update_worker.failed.connect(
            lambda msg: self.chat.add_system(tr("检查更新失败：") + msg)
        )
        self._update_worker.start()

    def _on_update_result(self, info) -> None:
        if not info:
            self.chat.add_system(tr("已是最新版本。"))
            self.statusBar().clearMessage()
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("发现新版本"))
        box.setText(tr("新版本 ") + info["version"] + tr(" 可用，是否下载并安装？"))
        yes = box.addButton(tr("下载并安装"), QMessageBox.AcceptRole)
        box.addButton(tr("取消"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self._download_update(info["url"])

    def _download_update(self, url: str) -> None:
        self.statusBar().showMessage(tr("正在下载更新…"))
        self._download_worker = DownloadWorker(url)
        self._download_worker.done.connect(self._on_download_done)
        self._download_worker.failed.connect(
            lambda msg: self.chat.add_system(tr("下载失败：") + msg)
        )
        self._download_worker.start()

    def _on_download_done(self, path: str) -> None:
        self.statusBar().showMessage(tr("下载完成，正在启动安装程序…"))
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            self.chat.add_system(tr("启动安装程序失败：") + str(exc))
            return
        self._force_quit = True
        self.close()

    def _quit_app(self) -> None:
        if self.project is not None and self.controller is not None:
            self.controller.quit()
            return
        self._force_quit = True
        self.close()

    # ---------- 关闭行为 ----------
    def closeEvent(self, event) -> None:  # noqa: N802
        if self.project is not None:
            self._save_layout()
            if not self._save_project():
                answer = QMessageBox.question(
                    self,
                    tr("关闭项目"),
                    tr("保存失败，仍然关闭项目吗？未保存的改动会丢失。"),
                )
                if answer != QMessageBox.Yes:
                    event.ignore()
                    return
            if self._autosave is not None:
                self._autosave.stop()
            try:
                self.project.close()
            finally:
                self.project = None
            self.closed.emit()
            event.accept()
            return
        self._save_layout()
        if self._force_quit or os.environ.get("TRUFFLE_SMOKE") == "1":
            event.accept()
            return
        behavior = self.settings.close_behavior
        if behavior == "ask":
            behavior = self._ask_close_behavior()
        if behavior == "minimize":
            event.ignore()
            self.showMinimized()
        elif behavior == "exit":
            event.accept()
        else:
            event.ignore()

    def _ask_close_behavior(self) -> str | None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("关闭 Truffle"))
        box.setIcon(QMessageBox.Question)
        box.setText(tr("关闭窗口时，你想最小化到任务栏，还是直接退出？"))
        min_btn = box.addButton(tr("最小化到任务栏"), QMessageBox.AcceptRole)
        exit_btn = box.addButton(tr("直接退出"), QMessageBox.DestructiveRole)
        box.addButton(tr("取消"), QMessageBox.RejectRole)
        remember = QCheckBox(tr("记住我的选择（可在「设置 → 常规设置」中修改）"))
        box.setCheckBox(remember)
        box.exec()
        clicked = box.clickedButton()
        if clicked is min_btn:
            choice = "minimize"
        elif clicked is exit_btn:
            choice = "exit"
        else:
            return None
        if remember.isChecked():
            self.settings.close_behavior = choice
            self.settings.save()
        return choice

    # ---------- 账号 / 社区 ----------
    def _account(self) -> Account:
        return Account(self.settings)

    def _enforce_login(self) -> None:
        if os.environ.get("TRUFFLE_SMOKE") == "1":
            return
        acc = self._account()
        if not self.settings.require_login or not acc.configured() or acc.logged_in():
            self._update_account_status()
            return
        dialog = AccountDialog(self)
        if dialog.exec() != AccountDialog.Accepted:
            self._force_quit = True
            self.close()
            return
        mode, username, password = dialog.result_credentials()
        if not self._do_login(mode, username, password):
            self._force_quit = True
            self.close()

    def _open_account(self) -> None:
        acc = self._account()
        if not acc.configured():
            self.chat.add_system(tr("尚未配置 LeanCloud（设置 → 常规设置）。"))
            return
        if acc.logged_in():
            box = QMessageBox(self)
            box.setWindowTitle(tr("账号"))
            box.setText(tr("已登录：") + acc.username)
            out_btn = box.addButton(tr("退出登录"), QMessageBox.DestructiveRole)
            box.addButton(tr("关闭"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is out_btn:
                acc.logout()
                acc.clear_session()
                self._update_account_status()
                self.chat.add_system(tr("已退出登录。"))
            return
        dialog = AccountDialog(self)
        if dialog.exec() != AccountDialog.Accepted:
            return
        mode, username, password = dialog.result_credentials()
        self._do_login(mode, username, password)

    def _do_login(self, mode: str, username: str, password: str) -> bool:
        if not username or not password:
            self.chat.add_system(tr("请输入账号与密码。"))
            return False
        acc = self._account()
        try:
            result = (
                acc.signup(username, password) if mode == "register" else acc.login(username, password)
            )
            acc.save_session(result)
            self._update_account_status()
            self.chat.add_system(tr("已登录：") + acc.username)
            return True
        except AccountError as exc:
            self.chat.add_system(tr("登录失败：") + str(exc))
            return False

    def _update_account_status(self) -> None:
        acc = self._account()
        if acc.logged_in():
            self.statusBar().showMessage(tr("已登录：") + acc.username)

    def _open_community(self) -> None:
        url = self.settings.community_url.strip()
        if not url:
            self.chat.add_system(tr("尚未配置社区地址（设置 → 常规设置）。"))
            return
        QDesktopServices.openUrl(QUrl(url))

    # ---------- 对话 ----------
    def _on_submit(self, text: str) -> None:
        if not self.ai_enabled:
            self.chat.add_system(tr("AI 已禁用，请先配置大模型或登录。"))
            return
        if not self.settings.is_configured:
            self.chat.add_system(tr("请先在「设置」里配置大模型 API Key。"))
            self._open_settings()
            if not self.settings.is_configured:
                return
        if not self.doc.is_loaded:
            self.chat.add_system(tr("请先打开一张图片。"))
            return
        try:
            llm = LLMClient(self.settings.llm)
        except Exception as exc:
            self.chat.add_system(str(exc))
            return
        if self._is_busy():
            self.chat.add_system(tr("正在处理，请稍候…"))
            return

        manual = self.params.active_jobs()
        self._commit_preview_silent()  # 把用户手动调节落进历史，AI 在其基础上继续
        self.params.reset_all()
        orchestrator = Orchestrator(
            self.doc, self.registry, llm, self.analyzer,
            style_id=self._agent_style,
            history_mode=self.settings.agent_history_mode,
        )
        self._agent_orchestrator = orchestrator
        self.chat.add_user(text)
        self._set_busy(True)

        vision_image = self.doc.current if self.settings.llm.vision else None
        self._worker = AgentWorker(
            orchestrator, text, vision_image, self.settings.llm.context,
            self.conversation, manual, self.summary,
        )
        self._worker.imageReady.connect(self._show_current)
        self._worker.imageReady.connect(self._refresh_all)
        self._worker.replied.connect(self.chat.add_assistant)
        self._worker.failed.connect(lambda msg: self.chat.add_system(tr("出错了：") + msg))
        self._worker.toolApplied.connect(self._on_agent_tool)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _set_busy(self, busy: bool) -> None:
        self.chat.set_busy(busy)
        self.params.set_busy(busy)
        self.canvas_tools.setEnabled(not busy)
        self.layers.setEnabled(not busy)

    def _on_worker_done(self) -> None:
        self._set_busy(False)
        if self.project is not None:
            orchestrator = self._agent_orchestrator
            if orchestrator is not None:
                try:
                    agent_path = self.project.workdir / "agent.json"
                    agent_path.write_text(
                        json.dumps(
                            {
                                "schema": 1,
                                "style": getattr(orchestrator, "style_id", "natural"),
                                "state": getattr(orchestrator, "last_state", {}),
                                "critique": getattr(orchestrator, "last_critique", None),
                                "jobs": getattr(orchestrator, "last_jobs", []),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            self.project.chat = {"summary": self.summary, "messages": self.conversation}
            self._mark_dirty()
            if self._pending_save:
                self._save_project()
        else:
            self.summary = session.save(self.summary, self.conversation)

    def _replay_conversation(self) -> None:
        for msg in self.conversation:
            role = msg.get("role")
            if role == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    text = content
                else:
                    text = next(
                        (p.get("text", "") for p in content if p.get("type") == "text"), ""
                    )
                if text:
                    self.chat.add_user(text)
            elif role == "assistant" and msg.get("content"):
                self.chat.add_assistant(msg["content"])

    def _clear_conversation(self) -> None:
        self.conversation = []
        self.summary = ""
        if self.project is not None:
            self.project.chat = {"summary": "", "messages": []}
            self._mark_dirty()
        else:
            session.clear()
        self.chat.clear()
        self.chat.add_system(tr("已开始新对话。"))

    def _on_agent_tool(self, name: str, params: dict) -> None:
        self.params.log(f"AI  ·  {tool_label(name)}  {params}", "#9be29b")
