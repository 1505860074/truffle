"""历史树：展示非破坏式历史步骤，可跳转 / 删除 / 修改参数。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.image_doc import Step
from . import theme
from .i18n import tr
from .tool_labels import tool_label


class HistoryPanel(QWidget):
    jumpRequested = Signal(int)   # 目标 pointer（0 = 原图）
    deleteRequested = Signal(int)  # 步骤下标
    editRequested = Signal(int)    # 步骤下标

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(170)
        self._kinds: list[str] = []
        self._readonly = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        title = QLabel(tr("历史"))
        title.setStyleSheet("font-weight:bold;")
        lay.addWidget(title)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemClicked.connect(self._clicked)
        lay.addWidget(self.tree, 1)
        self.apply_theme()

    def apply_theme(self) -> None:
        t = theme.current()
        self.setStyleSheet(
            f"QWidget{{background:{t['panel_bg']};color:{t['text']};}}"
            f"QTreeWidget{{background:{t['log_bg']};border:1px solid {t['border']};}}"
            "QTreeWidget::item{height:22px;}"
            f"QTreeWidget::item:selected{{background:{t['accent_bg']};color:{t['accent']};}}"
        )

    def set_readonly(self, readonly: bool) -> None:
        self._readonly = bool(readonly)

    # ---------- 刷新 ----------
    @staticmethod
    def _label(step: Step) -> str:
        if step.kind == "tool":
            return tr("工具 · ") + tool_label(step.data.get("name", ""))
        return tr(step.label)

    def refresh(self, doc) -> None:
        self.tree.clear()
        self._kinds = [s.kind for s in doc.steps()]
        root = QTreeWidgetItem(["原图"])
        root.setData(0, Qt.UserRole, -1)
        self.tree.addTopLevelItem(root)
        for i, step in enumerate(doc.steps()):
            item = QTreeWidgetItem([self._label(step)])
            item.setData(0, Qt.UserRole, i)
            self.tree.addTopLevelItem(item)
        target = self.tree.topLevelItem(doc.pointer())
        if target is not None:
            self.tree.setCurrentItem(target)

    # ---------- 交互 ----------
    def _clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        i = item.data(0, Qt.UserRole)
        self.jumpRequested.emit(0 if i == -1 else i + 1)

    def _menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        i = item.data(0, Qt.UserRole)
        menu = QMenu(self)
        jump = menu.addAction(tr("跳到此步"))
        edit = dele = None
        if i >= 0 and not self._readonly:
            if self._kinds[i] in ("tool", "crop"):
                edit = menu.addAction(tr("修改参数…"))
            dele = menu.addAction(tr("删除此步"))
        act = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if act is None:
            return
        if act is jump:
            self.jumpRequested.emit(0 if i == -1 else i + 1)
        elif edit is not None and act is edit:
            self.editRequested.emit(i)
        elif dele is not None and act is dele:
            self.deleteRequested.emit(i)
