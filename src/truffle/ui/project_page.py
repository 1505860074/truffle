"""项目加载页：新建 / 打开 / 导入 / 管理 `.truffle` 项目。"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

from ..config import AppSettings
from ..core.account import Account
from ..core.project import (
    PROJECT_EXT,
    RecentProjects,
    create_project,
    default_project_dir,
    merged_projects,
    move_to_recycle_bin,
    rename_project,
    set_project_cover,
)
from . import theme
from .account_dialog import AccountDialog
from .general_settings_dialog import GeneralSettingsDialog
from .i18n import set_language, tr

_INVALID_NAME = re.compile(r'[\\/:*?"<>|]')


def _fmt_time(timestamp: float) -> str:
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError):
        return ""


class NewProjectDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(tr("新建项目"))
        self.setMinimumWidth(460)

        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("例如：证件照精修"))
        self.location = QComboBox()
        self.location.addItem(tr("默认目录（文档\\Truffle Projects）"), "default")
        self.location.addItem(tr("选择其他位置…"), "custom")
        self.custom_dir = QLineEdit()
        self.custom_dir.setPlaceholderText(tr("选择项目保存目录"))
        browse = QPushButton(tr("浏览…"))
        browse.clicked.connect(self._browse)
        self.custom_dir.setEnabled(False)
        browse.setEnabled(False)
        self._browse_btn = browse
        self.location.currentIndexChanged.connect(self._on_location)

        custom_row = QWidget()
        custom_lay = QHBoxLayout(custom_row)
        custom_lay.setContentsMargins(0, 0, 0, 0)
        custom_lay.addWidget(self.custom_dir, 1)
        custom_lay.addWidget(browse)

        form = QVBoxLayout(self)
        form.addWidget(QLabel(tr("项目名称")))
        form.addWidget(self.name)
        form.addWidget(QLabel(tr("保存位置")))
        form.addWidget(self.location)
        form.addWidget(custom_row)
        self.preview = QLabel()
        self.preview.setStyleSheet("color:#888888;")
        self.preview.setWordWrap(True)
        form.addWidget(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)

        self.name.textChanged.connect(self._update_preview)
        self.location.currentIndexChanged.connect(self._update_preview)
        self.custom_dir.textChanged.connect(self._update_preview)
        self._update_preview()

    def _on_location(self, _index: int) -> None:
        custom = self.location.currentData() == "custom"
        self.custom_dir.setEnabled(custom)
        self._browse_btn.setEnabled(custom)
        self._update_preview()

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("选择项目保存目录"))
        if path:
            self.custom_dir.setText(path)

    def _folder(self) -> Path:
        if self.location.currentData() == "custom":
            raw = self.custom_dir.text().strip()
            if raw:
                return Path(raw)
        return default_project_dir(self.settings)

    def _target(self) -> Path:
        name = self.name.text().strip()
        if name.lower().endswith(PROJECT_EXT):
            name = name[: -len(PROJECT_EXT)]
        return self._folder() / (name + PROJECT_EXT)

    def _update_preview(self) -> None:
        name = self.name.text().strip()
        if not name:
            self.preview.setText(tr("请输入项目名称。"))
            return
        if _INVALID_NAME.search(name):
            self.preview.setText(tr("名称不能包含 \\ / : * ? \" < > |"))
            return
        self.preview.setText(tr("将保存到：") + str(self._target()))

    def _accept(self) -> None:
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, tr("新建项目"), tr("请输入项目名称。"))
            return
        if _INVALID_NAME.search(name):
            QMessageBox.warning(self, tr("新建项目"), tr("名称包含非法字符。"))
            return
        target = self._target()
        if target.exists():
            QMessageBox.warning(self, tr("新建项目"), tr("同名项目已存在，请改名或选择其他位置。"))
            return
        if not target.parent.exists():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.critical(self, tr("新建项目"), str(exc))
                return
        self.accept()

    def result_path(self) -> Path:
        return self._target()


class ProjectCard(QFrame):
    clicked = Signal(str)
    context = Signal(str, object)

    def __init__(self, info, parent=None) -> None:
        super().__init__(parent)
        self.info = info
        self.setObjectName("projectCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(250)
        self.setMaximumWidth(380)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        cover = QLabel()
        cover.setFixedHeight(150)
        cover.setAlignment(Qt.AlignCenter)
        cover.setObjectName("projectCover")
        if info.cover:
            pix = QPixmap()
            pix.loadFromData(info.cover)
            if not pix.isNull():
                cover.setPixmap(pix.scaled(280, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if cover.pixmap() is None or cover.pixmap().isNull():
            cover.setText("Truffle")
            cover.setStyleSheet("font-size:22px;font-weight:bold;")
        lay.addWidget(cover)

        name = QLabel(info.name or info.path.stem)
        name.setStyleSheet("font-weight:bold;font-size:14px;")
        name.setWordWrap(False)
        lay.addWidget(name)
        meta = _fmt_time(info.modified)
        if info.missing:
            meta = tr("文件不存在")
        elif info.error:
            meta = tr("项目损坏")
        sub = QLabel(meta)
        sub.setStyleSheet("color:#8b8b8b;")
        lay.addWidget(sub)
        path_label = QLabel(str(info.path))
        path_label.setStyleSheet("color:#777777;font-size:11px;")
        path_label.setWordWrap(True)
        lay.addWidget(path_label)

        if info.missing or info.error:
            self.setEnabled(True)
            self.setStyleSheet("QFrame#projectCard{opacity:0.55;}")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(str(self.info.path))
        elif event.button() == Qt.RightButton:
            self.context.emit(str(self.info.path), self.mapToGlobal(event.pos()))
        super().mousePressEvent(event)


class ProjectRow(QFrame):
    clicked = Signal(str)
    context = Signal(str, object)

    def __init__(self, info, parent=None) -> None:
        super().__init__(parent)
        self.info = info
        self.setObjectName("projectRow")
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(12)
        thumb = QLabel()
        thumb.setFixedSize(80, 50)
        thumb.setAlignment(Qt.AlignCenter)
        if info.cover:
            pix = QPixmap()
            pix.loadFromData(info.cover)
            if not pix.isNull():
                thumb.setPixmap(pix.scaled(80, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if thumb.pixmap() is None or thumb.pixmap().isNull():
            thumb.setText("T")
        lay.addWidget(thumb)
        name = QLabel(info.name or info.path.stem)
        name.setStyleSheet("font-weight:bold;")
        name.setMinimumWidth(180)
        lay.addWidget(name)
        status = tr("文件不存在") if info.missing else (tr("项目损坏") if info.error else _fmt_time(info.modified))
        state = QLabel(status)
        state.setStyleSheet("color:#8b8b8b;")
        state.setMinimumWidth(140)
        lay.addWidget(state)
        path = QLabel(str(info.path))
        path.setStyleSheet("color:#777777;")
        lay.addWidget(path, 1)
        if info.missing or info.error:
            self.setStyleSheet("QFrame#projectRow{opacity:0.55;}")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(str(self.info.path))
        elif event.button() == Qt.RightButton:
            self.context.emit(str(self.info.path), self.mapToGlobal(event.pos()))
        super().mousePressEvent(event)


class ProjectPage(QWidget):
    openRequested = Signal(str)
    quitRequested = Signal()

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.recent = RecentProjects()
        self._infos: list = []
        self._query = ""
        self._sort = "modified"
        self._view = settings.project_view if settings.project_view in ("card", "list") else "card"
        self.setWindowTitle("Truffle · " + tr("项目"))
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self.title = QLabel("Truffle")
        self.title.setStyleSheet("font-size:24px;font-weight:bold;")
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("搜索项目…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search)
        self.sort = QComboBox()
        self.sort.addItem(tr("修改时间（新→旧）"), "modified")
        self.sort.addItem(tr("修改时间（旧→新）"), "modified_asc")
        self.sort.addItem(tr("名称（A→Z）"), "name")
        self.sort.addItem(tr("名称（Z→A）"), "name_desc")
        self.sort.currentIndexChanged.connect(self._on_sort)
        self.view_btn = QToolButton()
        self.view_btn.setText(tr("卡片"))
        self.view_btn.setToolTip(tr("切换卡片/列表"))
        self.view_btn.clicked.connect(self._toggle_view)
        self.settings_btn = QToolButton()
        self.settings_btn.setText(tr("设置"))
        self.settings_btn.setPopupMode(QToolButton.InstantPopup)
        settings_menu = QMenu(self.settings_btn)
        settings_menu.addAction(tr("常规设置…"), self._open_settings)
        if self.settings.llm_enabled:
            settings_menu.addAction(tr("大模型配置…"), self._open_llm_settings)
        self.settings_btn.setMenu(settings_menu)
        self.account_btn = QToolButton()
        self.account_btn.setText(tr("账号"))
        self.account_btn.clicked.connect(self._open_account)
        self.community_btn = QToolButton()
        self.community_btn.setText(tr("社区"))
        self.community_btn.clicked.connect(self._open_community)

        top = QHBoxLayout()
        top.addWidget(self.title)
        top.addSpacing(20)
        top.addWidget(self.search, 1)
        top.addWidget(self.sort)
        top.addWidget(self.view_btn)
        top.addWidget(self.settings_btn)
        top.addWidget(self.account_btn)
        top.addWidget(self.community_btn)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.container = QWidget()
        self.scroll.setWidget(self.container)

        self.new_btn = QPushButton(tr("新建项目"))
        self.new_btn.clicked.connect(self._new_project)
        self.import_btn = QPushButton(tr("导入项目"))
        self.import_btn.clicked.connect(self._import_project)
        self.refresh_btn = QPushButton(tr("刷新"))
        self.refresh_btn.clicked.connect(self.refresh)
        self.status = QLabel()
        self.status.setStyleSheet("color:#8b8b8b;")
        bottom = QHBoxLayout()
        bottom.addWidget(self.new_btn)
        bottom.addWidget(self.import_btn)
        bottom.addWidget(self.refresh_btn)
        bottom.addWidget(self.status, 1)
        self.quit_btn = QPushButton(tr("退出"))
        self.quit_btn.clicked.connect(self.quitRequested.emit)
        bottom.addWidget(self.quit_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)
        root.addLayout(top)
        root.addWidget(self.scroll, 1)
        root.addLayout(bottom)

        self.apply_theme()
        self.refresh()

    # ---------- 主题 / 刷新 ----------
    def apply_theme(self) -> None:
        theme.apply_app_palette(QApplication.instance())
        t = theme.current()
        self.setStyleSheet(
            f"QWidget{{background:{t['window']};color:{t['window_text']};}}"
            f"QLineEdit,QComboBox,QSpinBox{{background:{t['base']};color:{t['text']};"
            f"border:1px solid {t['border']};border-radius:4px;padding:4px;}}"
            f"QPushButton{{background:{t['button']};color:{t['button_text']};"
            f"border:1px solid {t['border']};border-radius:5px;padding:6px 12px;}}"
            f"QPushButton:hover{{background:{t['accent_bg']};}}"
            f"QToolButton{{background:transparent;color:{t['text']};padding:4px;}}"
            f"QFrame#projectCard,QFrame#projectRow{{background:{t['panel_bg']};"
            f"border:1px solid {t['border']};border-radius:8px;}}"
            f"QFrame#projectCard:hover,QFrame#projectRow:hover{{border:1px solid {t['accent']};}}"
            f"QLabel#projectCover{{background:{t['canvas_bg']};border-radius:6px;}}"
        )

    def refresh(self) -> None:
        self.recent.load()
        self._infos = merged_projects(self.settings, self.recent)
        self._rebuild()
        self._update_account()
        self.status.setText(tr("共 ") + str(len(self._infos)) + tr(" 个项目"))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.quitRequested.emit()
        event.accept()

    def _filtered(self) -> list:
        items = list(self._infos)
        query = self._query.strip().lower()
        if query:
            items = [
                item for item in items
                if query in (item.name or "").lower() or query in str(item.path).lower()
            ]
        reverse = self._sort in ("modified", "name_desc")
        if self._sort in ("modified", "modified_asc"):
            items.sort(key=lambda item: item.modified, reverse=reverse)
        else:
            items.sort(key=lambda item: (item.name or "").lower(), reverse=reverse)
        return items

    def _rebuild(self) -> None:
        self.container = QWidget()
        self.scroll.setWidget(self.container)
        items = self._filtered()
        if not items:
            empty = QVBoxLayout(self.container)
            empty.addStretch(1)
            hint = QLabel(tr("还没有项目。点击「新建项目」开始，或导入一个 .truffle 文件。"))
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet("color:#8b8b8b;font-size:15px;")
            empty.addWidget(hint)
            empty.addStretch(1)
            return
        if self._view == "list":
            lay = QVBoxLayout(self.container)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
            for info in items:
                row = ProjectRow(info)
                row.clicked.connect(self._open_path)
                row.context.connect(self._menu)
                lay.addWidget(row)
            lay.addStretch(1)
            return
        lay = QGridLayout(self.container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        columns = 3
        for i, info in enumerate(items):
            card = ProjectCard(info)
            card.clicked.connect(self._open_path)
            card.context.connect(self._menu)
            lay.addWidget(card, i // columns, i % columns)
        lay.setRowStretch(lay.rowCount(), 1)
        lay.setColumnStretch(columns, 1)

    # ---------- 交互 ----------
    def _on_search(self, text: str) -> None:
        self._query = text
        self._rebuild()

    def _on_sort(self, _index: int) -> None:
        self._sort = str(self.sort.currentData())
        self._rebuild()

    def _toggle_view(self) -> None:
        self._view = "list" if self._view == "card" else "card"
        self.settings.project_view = self._view
        self.settings.save()
        self.view_btn.setText(tr("卡片") if self._view == "card" else tr("列表"))
        self._rebuild()

    def _open_path(self, path: str) -> None:
        info = next((item for item in self._infos if str(item.path) == path), None)
        if info is not None and (info.missing or info.error):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle(tr("项目不可用"))
            box.setText(
                tr("项目文件不存在或已损坏：") + "\n" + path + (
                    "\n\n" + info.error if info.error and not info.missing else ""
                )
            )
            remove = box.addButton(tr("移除记录"), QMessageBox.DestructiveRole)
            box.addButton(tr("取消"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is remove:
                self.recent.remove(path)
                self.refresh()
            return
        self.openRequested.emit(path)

    def _menu(self, path: str, global_pos) -> None:
        info = next((item for item in self._infos if str(item.path) == path), None)
        menu = QMenu(self)
        open_act = menu.addAction(tr("打开"))
        rename_act = menu.addAction(tr("重命名…"))
        delete_act = menu.addAction(tr("删除…"))
        cover_menu = menu.addMenu(tr("设置封面"))
        cover_active = cover_menu.addAction(tr("当前活动图"))
        cover_first = cover_menu.addAction(tr("第一张导入图"))
        cover_tiles = cover_menu.addAction(tr("最近 4 张拼合"))
        cover_custom = cover_menu.addAction(tr("选择自定义图片…"))
        show_act = menu.addAction(tr("在资源管理器中显示"))
        remove_act = None
        if info is not None and info.missing:
            remove_act = menu.addAction(tr("移除记录"))
        act = menu.exec(global_pos)
        if act is None:
            return
        if act is open_act:
            self._open_path(path)
        elif act is rename_act:
            self._rename(path)
        elif act is delete_act:
            self._delete(path)
        elif act in (cover_active, cover_first, cover_tiles, cover_custom):
            if info is None or info.missing:
                return
            mode = {cover_active: "active", cover_first: "first",
                    cover_tiles: "tiles", cover_custom: "custom"}[act]
            self._set_cover(path, mode)
        elif act is show_act:
            self._reveal(path)
        elif remove_act is not None and act is remove_act:
            self.recent.remove(path)
            self.refresh()

    def _rename(self, path: str) -> None:
        old = Path(path).stem
        name, ok = QInputDialog.getText(self, tr("重命名项目"), tr("新名称"), text=old)
        if not ok:
            return
        name = name.strip()
        if name.lower().endswith(PROJECT_EXT):
            name = name[: -len(PROJECT_EXT)]
        if not name or _INVALID_NAME.search(name):
            QMessageBox.warning(self, tr("重命名项目"), tr("名称无效。"))
            return
        try:
            new_path = rename_project(path, name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("重命名项目"), str(exc))
            return
        self.recent.remove(path)
        self.recent.add(new_path, name)
        self.refresh()

    def _delete(self, path: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("删除项目"))
        box.setText(tr("确定把项目移到回收站吗？") + "\n" + path)
        yes = box.addButton(tr("删除"), QMessageBox.DestructiveRole)
        box.addButton(tr("取消"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        try:
            move_to_recycle_bin(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("删除项目"), str(exc))
            return
        self.recent.remove(path)
        self.refresh()

    def _set_cover(self, path: str, mode: str) -> None:
        custom = None
        if mode == "custom":
            chosen, _ = QFileDialog.getOpenFileName(
                self, tr("选择封面图片"), "",
                "图片 (*.png *.jpg *.jpeg *.bmp *.webp)",
            )
            if not chosen:
                return
            try:
                custom = Path(chosen).read_bytes()
            except OSError as exc:
                QMessageBox.critical(self, tr("设置封面"), str(exc))
                return
        try:
            set_project_cover(path, mode, custom)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("设置封面"), str(exc))
            return
        self.refresh()

    def _reveal(self, path: str) -> None:
        try:
            subprocess.Popen(["explorer", "/select,", str(Path(path).resolve())])
        except Exception:  # noqa: BLE001
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _new_project(self) -> None:
        dialog = NewProjectDialog(self.settings, self)
        if dialog.exec() != NewProjectDialog.Accepted:
            return
        target = dialog.result_path()
        try:
            project = create_project(target, target.stem, cover_mode=self.settings.default_cover_mode)
            project.close()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("新建项目"), str(exc))
            return
        self.recent.add(target, target.stem)
        self.openRequested.emit(str(target))

    def _import_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("导入项目"), "", "Truffle 项目 (*.truffle);;所有文件 (*)"
        )
        if not path:
            return
        self.recent.add(path)
        self.refresh()
        self.openRequested.emit(path)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(PROJECT_EXT):
                self.recent.add(path)
                self.openRequested.emit(path)
                break

    # ---------- 顶部入口 ----------
    def _open_settings(self) -> None:
        dialog = GeneralSettingsDialog(self.settings, self)
        if dialog.exec() != GeneralSettingsDialog.Accepted:
            return
        self.settings.project_dir = dialog.result_project_dir()
        self.settings.autosave_interval = dialog.result_autosave()
        self.settings.history_steps = dialog.result_history_steps()
        self.settings.project_view = dialog.result_project_view()
        self.settings.default_cover_mode = dialog.result_cover_mode()
        self.settings.theme = dialog.result_theme()
        self.settings.language = dialog.result_language()
        self.settings.update_url = dialog.result_update_url()
        self.settings.auto_check_update = dialog.result_auto_check()
        self.settings.file_assoc = dialog.result_file_assoc()
        self.settings.project_assoc = dialog.result_project_assoc()
        (
            self.settings.lc_app_id,
            self.settings.lc_app_key,
            self.settings.lc_server_url,
        ) = dialog.result_leancloud()
        self.settings.require_login = dialog.result_require_login()
        self.settings.community_url = dialog.result_community_url()
        self.settings.save()
        theme.set_theme(self.settings.theme)
        set_language(self.settings.language)
        try:
            from ..core.shell import set_file_association, set_project_association

            set_file_association(self.settings.file_assoc)
            set_project_association(self.settings.project_assoc)
        except Exception:
            pass
        self._view = self.settings.project_view
        self.view_btn.setText(tr("卡片") if self._view == "card" else tr("列表"))
        self.apply_theme()
        self.refresh()

    def _open_llm_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        dialog = SettingsDialog(self.settings.llm, self)
        if dialog.exec() != SettingsDialog.Accepted:
            return
        self.settings.llm = dialog.result_settings()
        self.settings.save()

    def _update_account(self) -> None:
        acc = Account(self.settings)
        if acc.logged_in():
            self.account_btn.setText(tr("账号：") + acc.username)
        else:
            self.account_btn.setText(tr("账号"))

    def _open_account(self) -> None:
        acc = Account(self.settings)
        if not acc.configured():
            QMessageBox.information(self, tr("账号"), tr("尚未配置 LeanCloud（设置 → 常规设置）。"))
            return
        if acc.logged_in():
            box = QMessageBox(self)
            box.setWindowTitle(tr("账号"))
            box.setText(tr("已登录：") + acc.username)
            out = box.addButton(tr("退出登录"), QMessageBox.DestructiveRole)
            box.addButton(tr("关闭"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is out:
                acc.logout()
                acc.clear_session()
                self._update_account()
            return
        dialog = AccountDialog(self)
        if dialog.exec() != AccountDialog.Accepted:
            return
        mode, username, password = dialog.result_credentials()
        if not username or not password:
            return
        try:
            result = acc.signup(username, password) if mode == "register" else acc.login(username, password)
            acc.save_session(result)
            self._update_account()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("账号"), str(exc))

    def _open_community(self) -> None:
        url = self.settings.community_url.strip()
        if not url:
            QMessageBox.information(self, tr("社区"), tr("尚未配置社区地址（设置 → 常规设置）。"))
            return
        QDesktopServices.openUrl(QUrl(url))
