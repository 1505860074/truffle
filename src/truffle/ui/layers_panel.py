"""图层面板：图层列表、显隐、不透明度、混合模式与常用图层操作。"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..core.layers import BLEND_LABELS, BLEND_MODES
from . import theme
from .i18n import tr


def _thumb_bgra(image: np.ndarray, size: int = 44) -> QPixmap:
    rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
    h, w = rgba.shape[:2]
    if h <= 0 or w <= 0:
        return QPixmap()
    qimg = QImage(rgba.data, w, h, 4 * w, QImage.Format_RGBA8888).copy()
    scaled = qimg.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    canvas = QPixmap(size, size)
    canvas.fill(Qt.transparent)
    from PySide6.QtGui import QPainter

    p = QPainter(canvas)
    p.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return canvas


class LayersPanel(QWidget):
    activeChanged = Signal(int)          # 文档内图层下标（0=底）
    visibilityChanged = Signal(int, bool)
    opacityChanged = Signal(int)         # 0..100（实时）
    opacityCommitted = Signal()
    blendChanged = Signal(str)
    addRequested = Signal()
    duplicateRequested = Signal()
    deleteRequested = Signal()
    mergeRequested = Signal()
    flattenRequested = Signal()
    maskRequested = Signal()
    maskDeleteRequested = Signal()
    moveRequested = Signal(int)          # +1 上移，-1 下移
    renameRequested = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc = None
        self.setMinimumHeight(180)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(5)

        head = QHBoxLayout()
        title = QLabel(tr("图层"))
        title.setStyleSheet("font-weight:bold;")
        head.addWidget(title)
        head.addStretch(1)
        self.count = QLabel("1")
        self.count.setObjectName("tip")
        head.addWidget(self.count)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setIconSize(QSize(44, 44))
        self.list.setSpacing(1)
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.itemDoubleClicked.connect(self._on_rename)
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.blend = QComboBox()
        for name in BLEND_MODES:
            self.blend.addItem(tr(BLEND_LABELS[name]), name)
        self.blend.currentIndexChanged.connect(self._on_blend)
        row.addWidget(self.blend, 1)
        lay.addLayout(row)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel(tr("不透明度")))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(100)
        self.opacity.valueChanged.connect(self._on_opacity)
        self.opacity.sliderReleased.connect(self.opacityCommitted)
        op_row.addWidget(self.opacity, 1)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setFixedWidth(40)
        op_row.addWidget(self.opacity_label)
        lay.addLayout(op_row)

        btns = QHBoxLayout()
        btns.setSpacing(3)
        for text, tip, signal in (
            ("＋", tr("新建图层"), self.addRequested),
            ("复制", tr("复制图层"), self.duplicateRequested),
            ("删除", tr("删除图层"), self.deleteRequested),
            ("合并", tr("向下合并"), self.mergeRequested),
        ):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.setFixedHeight(26)
            btn.clicked.connect(signal)
            btns.addWidget(btn)
        lay.addLayout(btns)

        btns2 = QHBoxLayout()
        btns2.setSpacing(3)
        for text, tip, signal in (
            ("蒙版", tr("用当前选区创建图层蒙版"), self.maskRequested),
            ("删蒙版", tr("删除图层蒙版"), self.maskDeleteRequested),
            ("上移", tr("图层上移"), lambda: self.moveRequested.emit(1)),
            ("下移", tr("图层下移"), lambda: self.moveRequested.emit(-1)),
            ("拼合", tr("合并可见图层"), self.flattenRequested),
        ):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.setFixedHeight(26)
            btn.clicked.connect(signal)
            btns2.addWidget(btn)
        lay.addLayout(btns2)

        self.apply_theme()

    def apply_theme(self) -> None:
        t = theme.current()
        self.setStyleSheet(
            f"QWidget{{background:{t['panel_bg']};color:{t['text']};}}"
            f"QListWidget{{background:{t['log_bg']};border:1px solid {t['border']};}}"
            "QListWidget::item{height:50px;}"
            f"QListWidget::item:selected{{background:{t['accent_bg']};color:{t['accent']};}}"
            f"QComboBox,QSlider{{background:{t['base']};color:{t['text']};}}"
            f"QPushButton{{background:{t['button']};color:{t['button_text']};"
            f"border:1px solid {t['border']};border-radius:4px;padding:2px 4px;}}"
            f"QPushButton:hover{{background:{t['panel_bg']};}}"
            f"#tip{{color:{t['text_dim']};}}"
        )

    def refresh(self, doc) -> None:
        self._doc = doc
        active = doc.active_index if doc.is_loaded else 0
        layers = doc.layers() if doc.is_loaded else []
        self.list.blockSignals(True)
        self.list.clear()
        for index in range(len(layers) - 1, -1, -1):
            layer = layers[index]
            label = layer.name + ("  [蒙版]" if layer.mask is not None else "")
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, index)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked)
            item.setIcon(self._icon(layer))
            self.list.addItem(item)
        if layers:
            row = len(layers) - 1 - active
            self.list.setCurrentRow(row)
        self.list.blockSignals(False)
        self.count.setText(str(len(layers)))

        if layers:
            self.blend.setEnabled(True)
            self.opacity.setEnabled(True)
            layer = layers[active]
            self.blend.blockSignals(True)
            idx = self.blend.findData(layer.blend)
            self.blend.setCurrentIndex(max(0, idx))
            self.blend.blockSignals(False)
            self.opacity.blockSignals(True)
            self.opacity.setValue(int(round(layer.opacity * 100)))
            self.opacity_label.setText(f"{int(round(layer.opacity * 100))}%")
            self.opacity.blockSignals(False)
        else:
            self.blend.setEnabled(False)
            self.opacity.setEnabled(False)

    @staticmethod
    def _icon(layer) -> "QPixmap":
        thumb = _thumb_bgra(layer.thumbnail(64), 44)
        return thumb

    def _current_doc_index(self) -> int:
        item = self.list.currentItem()
        if item is None:
            return -1
        return int(item.data(Qt.UserRole))

    def _on_row_changed(self, _row: int) -> None:
        index = self._current_doc_index()
        if index >= 0:
            self.activeChanged.emit(index)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.UserRole)
        if index is None:
            return
        self.visibilityChanged.emit(int(index), item.checkState() == Qt.Checked)

    def _on_rename(self, item: QListWidgetItem) -> None:
        from PySide6.QtWidgets import QInputDialog

        index = item.data(Qt.UserRole)
        if index is None:
            return
        current = item.text().replace("  [??]", "")
        name, ok = QInputDialog.getText(self, tr("?????"), tr("??"), text=current)
        if ok and str(name).strip():
            self.renameRequested.emit(int(index), str(name).strip())

    def _on_blend(self, _index: int) -> None:
        self.blendChanged.emit(str(self.blend.currentData()))

    def _on_opacity(self, value: int) -> None:
        self.opacity_label.setText(f"{value}%")
        self.opacityChanged.emit(int(value))

    def set_mask_enabled(self, has_mask: bool) -> None:
        # 蒙版按钮仍是可用的；这里只更新提示状态
        self.setToolTip(tr("有图层蒙版") if has_mask else "")
