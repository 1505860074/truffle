"""画布工具栏：工具选择（第一行）+ 选区/变换选项（第二行）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.selection import SELECTION_MODE_LABELS, SELECTION_MODES
from . import theme
from .i18n import tr


class CanvasToolBar(QWidget):
    toolSelected = Signal(str)
    applyRequested = Signal()
    cancelRequested = Signal()
    featherChanged = Signal(float)
    toleranceChanged = Signal(int)
    contiguousChanged = Signal(bool)
    selectionModeChanged = Signal(str)
    zoomRequested = Signal(str)
    flipRequested = Signal(bool)
    rotateRequested = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "view"
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 3, 6, 3)
        root.setSpacing(3)

        # ---------- 第一行：工具 ----------
        row1 = QHBoxLayout()
        row1.setSpacing(3)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        tools = [
            ("move", "移动", "V"),
            ("rect", "矩形", "M"),
            ("ellipse", "椭圆", "Shift+M"),
            ("lasso", "套索", "L"),
            ("polygon", "多边形", "Shift+L"),
            ("wand", "魔棒", "W"),
            ("crop", "裁剪", "C"),
            ("liquify", "液化", "B"),
            ("transform", "变换", "Ctrl+T"),
            ("hand", "抓手", "Space"),
            ("zoom", "缩放", "Z"),
        ]
        for key, label, shortcut in tools:
            btn = QToolButton()
            btn.setText(tr(label))
            btn.setCheckable(True)
            btn.setToolTip(tr(label) + (f"（{shortcut}）" if shortcut else ""))
            btn.setAutoRaise(True)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _=False, k=key: self.toolSelected.emit(k))
            self._buttons[key] = btn
            self._group.addButton(btn)
            row1.addWidget(btn)
        row1.addStretch(1)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(44)
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row1.addWidget(self.zoom_label)
        root.addLayout(row1)

        # ---------- 第二行：选项 ----------
        row2 = QHBoxLayout()
        row2.setSpacing(5)
        self._row2 = QWidget()
        self._row2.setLayout(row2)
        self._sel_widgets: list[QWidget] = []

        feather_label = QLabel(tr("羽化"))
        row2.addWidget(feather_label)
        self._sel_widgets.append(feather_label)
        self.feather = QDoubleSpinBox()
        self.feather.setRange(0, 250)
        self.feather.setDecimals(0)
        self.feather.setSingleStep(2)
        self.feather.setFixedWidth(58)
        self.feather.valueChanged.connect(lambda v: self.featherChanged.emit(float(v)))
        row2.addWidget(self.feather)
        self._sel_widgets.append(self.feather)

        mode_label = QLabel(tr("模式"))
        row2.addWidget(mode_label)
        self._sel_widgets.append(mode_label)
        self.sel_mode = QComboBox()
        for mode in SELECTION_MODES:
            self.sel_mode.addItem(tr(SELECTION_MODE_LABELS[mode]), mode)
        self.sel_mode.setFixedWidth(110)
        self.sel_mode.currentIndexChanged.connect(
            lambda _=0: self.selectionModeChanged.emit(str(self.sel_mode.currentData()))
        )
        row2.addWidget(self.sel_mode)
        self._sel_widgets.append(self.sel_mode)

        tol_label = QLabel(tr("容差"))
        row2.addWidget(tol_label)
        self._sel_widgets.append(tol_label)
        self.tolerance = QSpinBox()
        self.tolerance.setRange(0, 255)
        self.tolerance.setValue(32)
        self.tolerance.setFixedWidth(56)
        self.tolerance.valueChanged.connect(lambda v: self.toleranceChanged.emit(int(v)))
        row2.addWidget(self.tolerance)
        self._sel_widgets.append(self.tolerance)

        self.contiguous = QCheckBox(tr("??"))
        self.contiguous.setChecked(True)
        self.contiguous.setFocusPolicy(Qt.NoFocus)
        self.contiguous.toggled.connect(self.contiguousChanged)
        row2.addWidget(self.contiguous)
        self._sel_widgets.append(self.contiguous)

        row2.addStretch(1)
        self.flip_h = QToolButton()
        self.flip_h.setText(tr("水平翻转"))
        self.flip_h.setFocusPolicy(Qt.NoFocus)
        self.flip_h.clicked.connect(lambda: self.flipRequested.emit(True))
        self.flip_v = QToolButton()
        self.flip_v.setText(tr("垂直翻转"))
        self.flip_v.setFocusPolicy(Qt.NoFocus)
        self.flip_v.clicked.connect(lambda: self.flipRequested.emit(False))
        row2.addWidget(self.flip_h)
        row2.addWidget(self.flip_v)

        self.apply_btn = QPushButton(tr("应用"))
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.setFocusPolicy(Qt.NoFocus)
        self.apply_btn.clicked.connect(self.applyRequested)
        self.cancel_btn = QPushButton(tr("取消"))
        self.cancel_btn.setFocusPolicy(Qt.NoFocus)
        self.cancel_btn.clicked.connect(self.cancelRequested)
        row2.addWidget(self.apply_btn)
        row2.addWidget(self.cancel_btn)

        root.addWidget(self._row2)
        self.set_mode("view")
        self.apply_theme()

    def apply_theme(self) -> None:
        t = theme.current()
        self.setStyleSheet(
            f"CanvasToolBar{{background:{t['panel_bg']};}}"
            f"QToolButton{{color:{t['button_text']};background:transparent;"
            "border:1px solid transparent;border-radius:4px;padding:3px 6px;}"
            f"QToolButton:hover{{background:{t['button']};border-color:{t['border']};}}"
            f"QToolButton:checked{{background:{t['accent_bg']};border-color:{t['accent']};"
            f"color:{t['accent']};}}"
            f"QLabel{{color:{t['text_dim']};}}"
            f"QComboBox,QSpinBox,QDoubleSpinBox{{background:{t['base']};color:{t['text']};"
            f"border:1px solid {t['border']};border-radius:3px;padding:1px 3px;}}"
            f"QPushButton{{background:{t['button']};color:{t['button_text']};"
            f"border:1px solid {t['border']};border-radius:4px;padding:3px 10px;}}"
            f"QPushButton#applyBtn{{background:{t['accent_bg']};border-color:{t['accent']};"
            f"color:{t['accent']};}}"
        )

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        modal = mode in ("crop", "liquify", "transform")
        for btn in (self.apply_btn, self.cancel_btn):
            btn.setVisible(modal)
        for btn in (self.flip_h, self.flip_v):
            btn.setVisible(mode == "transform")
        show_sel = mode == "select"
        for widget in self._sel_widgets:
            widget.setVisible(show_sel)
        self._row2.setVisible(show_sel or modal)
        for key in ("rect", "ellipse", "lasso", "polygon", "wand"):
            self._buttons[key].setVisible(mode in ("view", "select"))
        if mode == "select":
            key = self._current_selection_tool()
            if key in self._buttons:
                self._buttons[key].setChecked(True)
        elif mode == "view":
            self._buttons["move"].setChecked(True)
        elif mode == "crop":
            self._buttons["crop"].setChecked(True)
        elif mode == "liquify":
            self._buttons["liquify"].setChecked(True)
        elif mode == "transform":
            self._buttons["transform"].setChecked(True)
        elif mode in ("hand", "zoom"):
            self._buttons[mode].setChecked(True)

    def _current_selection_tool(self) -> str:
        return getattr(self, "_sel_tool", "rect")

    def set_selection_tool(self, tool: str) -> None:
        self._sel_tool = tool
        if tool in self._buttons and self._mode in ("view", "select"):
            self._buttons[tool].setChecked(True)

    def set_zoom(self, scale: float) -> None:
        self.zoom_label.setText(f"{scale * 100:.0f}%")

    def feather_value(self) -> float:
        return float(self.feather.value())

    def tolerance_value(self) -> int:
        return int(self.tolerance.value())

    def selection_mode(self) -> str:
        return str(self.sel_mode.currentData())
