"""文件库：把一组待修图片集中管理。

- 第一个格子是浅黄圆角「+」方块（与缩略图等大、随列表滚动），单击即添加图片；
- 缩略图悬停时右上角出现「×」可单独删除；支持 Ctrl/Shift 多选后：
  Delete 键 / 右键菜单 / 右上角「删除选中 (n)」按钮 一起删除；
- 点击缩略图 → 发出 `fileChosen(path)`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QWidget,
)

from . import theme
from .i18n import tr
from .naming import area_name
from .watermark import Watermark

IMAGE_FILTER = "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)"
ICON_PX = 96
_CLOSE_PX = 16


def _plus_cell(size: int = ICON_PX, bg: str = "#f3e2a8", fg: str = "#3a2716") -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(bg))
    p.drawRoundedRect(0, 0, size, size, 12, 12)
    pen = QPen(QColor(fg))
    pen.setWidthF(size * 0.09)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    m = size * 0.30
    c = size / 2.0
    p.drawLine(int(m), int(c), int(size - m), int(c))
    p.drawLine(int(c), int(m), int(c), int(size - m))
    p.end()
    return QIcon(pm)


class _LibraryList(QListWidget):
    """缩略图列表：悬停画「×」、Delete 键删除选中。"""

    deleteClicked = Signal(str)
    deleteSelected = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._hover: QListWidgetItem | None = None

    @staticmethod
    def _is_image(item: QListWidgetItem | None) -> bool:
        return item is not None and item.data(Qt.UserRole) is not None

    def _close_rect(self, item: QListWidgetItem) -> QRect:
        r = self.visualItemRect(item)
        return QRect(r.right() - _CLOSE_PX - 2, r.top() + 2, _CLOSE_PX, _CLOSE_PX)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        item = self.itemAt(event.pos())
        self._hover = item if self._is_image(item) else None
        self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = None
        self.viewport().update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        item = self.itemAt(event.pos())
        if self._is_image(item) and self._close_rect(item).contains(event.pos()):
            self.deleteClicked.emit(item.data(Qt.UserRole))
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.deleteSelected.emit()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._hover is None:
            return
        r = self._close_rect(self._hover)
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f3e2a8"))
        p.drawRoundedRect(r, 4, 4)
        pen = QPen(QColor("#3a2716"))
        pen.setWidthF(1.8)
        p.setPen(pen)
        m = 4
        p.drawLine(r.left() + m, r.top() + m, r.right() - m, r.bottom() - m)
        p.drawLine(r.right() - m, r.top() + m, r.left() + m, r.bottom() - m)
        p.end()


class FileLibrary(QWidget):
    fileChosen = Signal(str)
    deleteRequested = Signal(object)  # list[str]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths: list[str] = []
        self.path_mapper: Callable[[str], str] | None = None
        self.setMinimumHeight(140)
        self.setObjectName("fileLibrary")

        self.list = _LibraryList()
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(ICON_PX, ICON_PX))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setFlow(QListWidget.LeftToRight)
        self.list.setSpacing(8)
        self.list.setWordWrap(True)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.itemClicked.connect(self._on_clicked)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.deleteClicked.connect(lambda path: self.deleteRequested.emit([path]))
        self.list.deleteSelected.connect(self._delete_selected)
        self.list.itemSelectionChanged.connect(self._update_delete_btn)

        # 第一个格子：加号（与缩略图等大、随列表滚动、单击添加）
        t0 = theme.current()
        self._add_item = QListWidgetItem(
            _plus_cell(ICON_PX, str(t0["add_bg"]), str(t0["add_fg"])), tr("添加图片")
        )
        self._add_item.setData(Qt.UserRole, None)
        self._add_item.setFlags(Qt.ItemIsEnabled)
        self._add_item.setToolTip(tr("添加图片到文件库"))
        self.list.addItem(self._add_item)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.addWidget(self.list, 1)

        # 右上角浮动「删除选中 (n)」按钮
        self.delete_btn = QPushButton(f"{tr('删除选中')} (0)", self)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(
            "QPushButton { background:#7a2f2f; color:#ffffff; border:none; "
            "border-radius:4px; padding:3px 8px; } "
            "QPushButton:hover { background:#8f3a3a; }"
        )
        self.delete_btn.clicked.connect(self._delete_selected)
        self.delete_btn.hide()

        self.watermark = Watermark(
            area_name("files"), self.list.viewport(), point_size=24,
            alpha=int(theme.current()["watermark_alpha"]), color=str(theme.current()["watermark"]),
        )
        self.apply_theme()

    def apply_theme(self) -> None:
        t = theme.current()
        self.setStyleSheet(
            f"#fileLibrary {{ border:1px solid {t['border']}; border-radius:6px; "
            f"background:{t['panel_bg']}; }}"
        )
        self._add_item.setIcon(_plus_cell(ICON_PX, str(t["add_bg"]), str(t["add_fg"])))
        self.watermark.set_color(str(t["watermark"]), int(t["watermark_alpha"]))

    # ---------- 对外 ----------
    def add_paths(self, paths: list[str]) -> list[str]:
        added: list[str] = []
        for p in paths:
            mapped = self.path_mapper(str(Path(p))) if self.path_mapper is not None else str(Path(p))
            rp = str(Path(mapped))
            if rp in self._paths:
                continue
            item = QListWidgetItem(self._thumb(rp), Path(rp).name)
            item.setData(Qt.UserRole, rp)
            item.setToolTip(rp)
            self.list.addItem(item)
            self._paths.append(rp)
            added.append(rp)
        return added

    def remove_paths(self, paths: list[str]) -> None:
        targets = {str(Path(p)) for p in paths}
        for i in range(self.list.count() - 1, -1, -1):
            item = self.list.item(i)
            if item.data(Qt.UserRole) in targets:
                self.list.takeItem(i)
        self._paths = [p for p in self._paths if p not in targets]
        self._update_delete_btn()

    def set_current(self, path: str) -> None:
        rp = str(Path(path))
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.UserRole) == rp:
                self.list.setCurrentItem(item)
                return

    def current_path(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if self.list._is_image(item) else None

    def selected_paths(self) -> list[str]:
        return [
            it.data(Qt.UserRole)
            for it in self.list.selectedItems()
            if it.data(Qt.UserRole) is not None
        ]

    def count(self) -> int:
        return len(self._paths)

    def paths(self) -> list[str]:
        return list(self._paths)

    # ---------- 内部 ----------
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_delete_btn()

    def _place_delete_btn(self) -> None:
        self.delete_btn.adjustSize()
        self.delete_btn.move(self.width() - self.delete_btn.width() - 12, 10)
        self.delete_btn.raise_()

    def _update_delete_btn(self) -> None:
        n = len(self.selected_paths())
        self.delete_btn.setText(f"{tr('删除选中')} ({n})")
        self.delete_btn.setVisible(n > 0)
        self._place_delete_btn()

    def _pick(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, tr("添加图片到文件库"), "", IMAGE_FILTER)
        if not paths:
            return
        added = self.add_paths(paths)
        if added and self.current_path() is None:
            self.set_current(added[0])
            self.fileChosen.emit(added[0])

    def _on_clicked(self, item: QListWidgetItem) -> None:
        if item.data(Qt.UserRole) is None:
            self._pick()
            return
        self.fileChosen.emit(item.data(Qt.UserRole))

    def _delete_selected(self) -> None:
        paths = self.selected_paths()
        if paths:
            self.deleteRequested.emit(paths)

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if self.list._is_image(item) and not item.isSelected():
            self.list.clearSelection()
            item.setSelected(True)
        paths = self.selected_paths()
        if not paths:
            return
        menu = QMenu(self)
        act = menu.addAction(f"{tr('删除选中')} ({len(paths)})")
        chosen = menu.exec(self.list.viewport().mapToGlobal(pos))
        if chosen is act:
            self._delete_selected()

    @staticmethod
    def _thumb(path: str) -> QIcon:
        pix = QPixmap(path)
        if pix.isNull():
            return QIcon()
        return QIcon(
            pix.scaled(ICON_PX, ICON_PX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
