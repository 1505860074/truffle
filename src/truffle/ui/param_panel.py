"""参数栏：按模块分类的功能面板，所见即所得。

- 模块（仿美图秀秀）：人像 / 调色 / 构图 / 形体 / 特效，每个模块下是子功能；
- 所见即所得：拖动任意滑块即实时渲染预览（去抖 + 后台线程）；顶部「应用」把预览写入历史，「重置」清空所有调节；
- 裁剪 / 液化 也在这里触发（鼠标交互仍在画布上完成）。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..tools.base import ToolParameter
from ..tools.registry import ToolRegistry
from . import theme
from .i18n import tr
from .naming import area_name
from .tool_labels import enum_label, param_label, tool_label
from .watermark import Watermark


def _qss(t: dict) -> str:
    return f"""
QGroupBox {{
    color: {t['accent']}; border: 1px solid {t['border']}; border-radius: 6px;
    margin-top: 10px; padding: 8px 6px 6px 6px; background: {t['panel_bg']};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QLabel {{ color: {t['text']}; }}
QSlider::groove:horizontal {{ height: 4px; background: {t['border']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; margin: -5px 0; border-radius: 6px; background: {t['accent']}; }}
QPushButton {{
    background: {t['button']}; color: {t['button_text']}; border: 1px solid {t['border']};
    border-radius: 4px; padding: 3px 10px;
}}
QPushButton:hover {{ background: {t['panel_bg']}; }}
QPushButton:disabled {{ color: {t['text_dim']}; border-color: {t['border']}; }}
#applyBtn {{ background: {t['accent_bg']}; border-color: {t['accent']}; color: {t['accent']}; }}
QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox {{
    background: {t['base']}; color: {t['text']}; border: 1px solid {t['border']};
    border-radius: 3px; padding: 1px 4px;
}}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: {t['button']}; color: {t['text']}; padding: 5px 10px;
    border: 1px solid {t['border']}; border-bottom: none; border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{ background: {t['accent_bg']}; color: {t['accent']}; }}
#logView {{ background: {t['log_bg']}; color: {t['log_text']}; border: 1px solid {t['border']}; }}
#status {{ color: {t['text_dim']}; }}
#tip {{ color: {t['text_dim']}; }}
"""

# 模块 → 子功能（工具名）
CATEGORIES: list[tuple[str, list[str]]] = [
    ("人像", [
        "skin_smooth", "whiten", "slim_face", "enlarge_eyes",
        "remove_blemish", "teeth_whiten", "remove_dark_circles",
        "eye_brighten", "iris", "face_light", "hair_color", "hair_enhance", "lipstick",
    ]),
    ("调色", [
        "exposure", "levels", "color_adjust", "color_temp", "hsl", "curves",
        "tone_recovery", "dehaze", "hdr", "sharpen_clarity", "noise_reduction",
        "vignette", "film",
    ]),
    ("局部", ["local_adjust", "dodge_burn", "clone"]),
    ("构图", ["rotate_flip"]),
    ("形体", ["body_slim", "leg_lengthen"]),
    ("特效", ["background_blur", "distort"]),
]

# 预览与导出共用的管线顺序：先调色影调 → 人像 → 形体 → 特效 → 构图（旋转放最后）
PIPELINE_ORDER = [
    "exposure", "levels", "color_adjust", "color_temp", "hsl", "curves",
    "tone_recovery", "dehaze", "hdr", "sharpen_clarity", "noise_reduction",
    "vignette", "film",
    "skin_smooth", "whiten", "remove_blemish", "teeth_whiten", "remove_dark_circles",
    "eye_brighten", "iris", "face_light", "hair_color", "hair_enhance", "lipstick",
    "local_adjust", "dodge_burn", "clone",
    "slim_face", "enlarge_eyes",
    "body_slim", "leg_lengthen",
    "background_blur", "distort",
    "rotate_flip",
]


class _ResetSlider(QSlider):
    """双击复位的滑块。"""

    doubleClicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class _ParamRow(QWidget):
    """单个参数的一行编辑器（滑块 + 数值框；双击滑块复位默认值）。"""

    changed = Signal()

    def __init__(self, param: ToolParameter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.param = param
        self._guard = False
        self.slider: QSlider | None = None
        self.editor: QWidget | None = None
        self._mn = 0.0
        self._mx = 1.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.label = QLabel(param_label(param.name))
        self.label.setFixedWidth(64)
        self.label.setToolTip(f"{param.name}：{param.description}")
        layout.addWidget(self.label)

        self._build_editor(param, layout)
        self.set_value(param.default if param.default is not None else self._initial())

    def _initial(self) -> Any:
        if self.param.enum:
            return self.param.enum[0]
        return self.param.minimum or 0

    def _build_editor(self, p: ToolParameter, layout: QHBoxLayout) -> None:
        if p.type in ("number", "integer"):
            mn = float(p.minimum) if p.minimum is not None else 0.0
            mx = float(p.maximum) if p.maximum is not None else 1.0
            if mx <= mn:
                mx = mn + 1.0
            self._mn, self._mx = mn, mx

            self.slider = _ResetSlider(Qt.Horizontal)
            self.slider.setRange(0, 1000)
            self.slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.slider.setToolTip("双击复位为默认值")
            self.slider.doubleClicked.connect(self._reset_default)

            if p.type == "integer":
                box: QSpinBox | QDoubleSpinBox = QSpinBox()
                box.setSingleStep(1)
            else:
                box = QDoubleSpinBox()
                box.setDecimals(2)
                box.setSingleStep(0.01)
            box.setRange(mn, mx)
            box.setFixedWidth(74)
            box.setKeyboardTracking(False)

            self.slider.valueChanged.connect(self._slider_changed)
            box.valueChanged.connect(self._spin_changed)
            self.editor = box
            layout.addWidget(self.slider, 1)
            layout.addWidget(box)

        elif p.type == "boolean":
            check = QCheckBox()
            check.toggled.connect(lambda _: self._edited())
            self.editor = check
            layout.addWidget(check)
            layout.addStretch(1)

        elif p.enum:
            combo = QComboBox()
            for item in p.enum:
                combo.addItem(enum_label(item), item)
            combo.currentIndexChanged.connect(lambda _: self._edited())
            self.editor = combo
            layout.addWidget(combo, 1)

        else:
            edit = QLineEdit()
            edit.textChanged.connect(lambda _: self._edited())
            self.editor = edit
            layout.addWidget(edit, 1)

    def _edited(self) -> None:
        if self._guard:
            return
        self.set_highlight()
        self.changed.emit()

    def _reset_default(self) -> None:
        if self.param.default is None:
            return
        self.set_value(self.param.default)
        self._edited()

    def _to_slider(self, value: float) -> int:
        if self._mx <= self._mn:
            return 0
        ratio = (float(value) - self._mn) / (self._mx - self._mn)
        return int(round(max(0.0, min(1.0, ratio)) * 1000))

    def _from_slider(self, pos: int) -> float:
        return self._mn + (self._mx - self._mn) * pos / 1000.0

    def _slider_changed(self, pos: int) -> None:
        if self._guard or self.editor is None:
            return
        self._guard = True
        self._set_editor_value(self._from_slider(pos))
        self._guard = False
        self._edited()

    def _spin_changed(self, value: float) -> None:
        if self._guard or self.slider is None:
            return
        self._guard = True
        self.slider.setValue(self._to_slider(value))
        self._guard = False
        self._edited()

    def _set_editor_value(self, value: Any) -> None:
        if self.param.type in ("number", "integer"):
            assert isinstance(self.editor, (QSpinBox, QDoubleSpinBox))
            self.editor.setValue(value)
        elif self.param.type == "boolean":
            assert isinstance(self.editor, QCheckBox)
            self.editor.setChecked(bool(value))
        elif self.param.enum:
            assert isinstance(self.editor, QComboBox)
            idx = self.editor.findData(value)
            self.editor.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            assert isinstance(self.editor, QLineEdit)
            self.editor.setText(str(value))

    # ---------- 对外 ----------
    def value(self) -> Any:
        if self.param.type in ("number", "integer"):
            assert isinstance(self.editor, (QSpinBox, QDoubleSpinBox))
            return self.editor.value()
        if self.param.type == "boolean":
            assert isinstance(self.editor, QCheckBox)
            return self.editor.isChecked()
        if self.param.enum:
            assert isinstance(self.editor, QComboBox)
            data = self.editor.currentData()
            return data if data is not None else self.editor.currentText()
        assert isinstance(self.editor, QLineEdit)
        return self.editor.text()

    def set_value(self, value: Any) -> None:
        if value is None:
            return
        self._guard = True
        if self.param.type in ("number", "integer"):
            v = max(self._mn, min(self._mx, float(value)))
            if self.param.type == "integer":
                v = int(round(v))
            self._set_editor_value(v)
            if self.slider is not None:
                self.slider.setValue(self._to_slider(v))
        else:
            self._set_editor_value(value)
        self._guard = False

    def is_default(self) -> bool:
        default = self.param.default
        value = self.value()
        if isinstance(value, float) and isinstance(default, (int, float)):
            return abs(value - float(default)) < 1e-6
        return value == default

    def set_highlight(self) -> None:
        self.label.setStyleSheet("color: #e7c87e; font-weight: bold;")
        QTimer.singleShot(1200, lambda: self.label.setStyleSheet(""))


class ToolParamGroup(QGroupBox):
    """一个子功能的参数组（无「应用」按钮，改动即预览）。"""

    changed = Signal()

    def __init__(self, tool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(tool_label(tool.name))
        self.setToolTip(f"{tool.name}：{tool.description}")
        self.tool_name = tool.name
        self.rows: dict[str, _ParamRow] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 6, 8, 6)
        for p in tool.parameters:
            row = _ParamRow(p)
            row.changed.connect(self.changed)
            self.rows[p.name] = row
            layout.addWidget(row)

    def values(self) -> dict[str, Any]:
        return {name: row.value() for name, row in self.rows.items()}

    def set_values(self, params: dict[str, Any]) -> None:
        for name, value in params.items():
            row = self.rows.get(name)
            if row is not None:
                row.set_value(value)

    def is_default(self) -> bool:
        return all(row.is_default() for row in self.rows.values())

    def reset_defaults(self) -> None:
        for row in self.rows.values():
            if row.param.default is not None:
                row.set_value(row.param.default)

    def set_busy(self, busy: bool) -> None:
        self.setEnabled(not busy)


class _CropControl(QGroupBox):
    start = Signal()
    apply = Signal()
    cancel = Signal()

    def __init__(self) -> None:
        super().__init__(tr("裁剪"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        self.btn = QPushButton(tr("开始裁剪"))
        self.btn.clicked.connect(self.start)
        lay.addWidget(self.btn)

        self.apply_btn = QPushButton(tr("应用裁剪"))
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.clicked.connect(self.apply)
        self.cancel_btn = QPushButton(tr("取消"))
        self.cancel_btn.clicked.connect(self.cancel)
        row = QHBoxLayout()
        row.addWidget(self.apply_btn)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self.apply_btn.setVisible(False)
        self.cancel_btn.setVisible(False)

        tip = QLabel(tr("在画布上拖拽选择要保留的区域，然后点「应用裁剪」。"))
        tip.setObjectName("tip")
        tip.setWordWrap(True)
        lay.addWidget(tip)

    def set_mode(self, mode: str) -> None:
        active = mode == "crop"
        self.btn.setVisible(not active)
        self.apply_btn.setVisible(active)
        self.cancel_btn.setVisible(active)


class _LiquifyControl(QGroupBox):
    start = Signal(float, float)  # radius, strength
    apply = Signal()
    cancel = Signal()

    def __init__(self) -> None:
        super().__init__(tr("液化"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel(tr("笔刷")))
        self.size = QSpinBox()
        self.size.setRange(10, 500)
        self.size.setValue(80)
        self.size.setSuffix(" px")
        size_row.addWidget(self.size, 1)
        lay.addLayout(size_row)

        str_row = QHBoxLayout()
        str_row.addWidget(QLabel(tr("强度")))
        self.strength = QDoubleSpinBox()
        self.strength.setRange(0.05, 1.0)
        self.strength.setSingleStep(0.05)
        self.strength.setValue(0.5)
        str_row.addWidget(self.strength, 1)
        lay.addLayout(str_row)

        self.btn = QPushButton(tr("开始液化"))
        self.btn.clicked.connect(lambda: self.start.emit(self.size.value(), self.strength.value()))
        lay.addWidget(self.btn)

        self.apply_btn = QPushButton(tr("应用液化"))
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.clicked.connect(self.apply)
        self.cancel_btn = QPushButton(tr("取消"))
        self.cancel_btn.clicked.connect(self.cancel)
        row = QHBoxLayout()
        row.addWidget(self.apply_btn)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self.apply_btn.setVisible(False)
        self.cancel_btn.setVisible(False)

        tip = QLabel(tr("按住鼠标在画布上拖动推挤像素，然后点「应用液化」。"))
        tip.setObjectName("tip")
        tip.setWordWrap(True)
        lay.addWidget(tip)

    def set_mode(self, mode: str) -> None:
        active = mode == "liquify"
        self.btn.setVisible(not active)
        self.apply_btn.setVisible(active)
        self.cancel_btn.setVisible(active)


class _SelectionControl(QGroupBox):
    select = Signal()
    clear = Signal()

    def __init__(self) -> None:
        super().__init__(tr("局部选区"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        self.btn = QPushButton(tr("开始选区"))
        self.btn.clicked.connect(self.select)
        lay.addWidget(self.btn)
        self.clear_btn = QPushButton(tr("清除选区"))
        self.clear_btn.clicked.connect(self.clear)
        lay.addWidget(self.clear_btn)
        self.state = QLabel(tr("未选区"))
        self.state.setObjectName("tip")
        lay.addWidget(self.state)
        tip = QLabel(tr("在画布上拖拽出一个区域，之后的调节只作用于该区域。"))
        tip.setObjectName("tip")
        tip.setWordWrap(True)
        lay.addWidget(tip)

    def set_active(self, active: bool) -> None:
        self.state.setText(tr("已启用选区") if active else tr("未选区"))


class ParamPanel(QWidget):
    previewChanged = Signal(object)          # list[(tool_name, params)]
    cropRequested = Signal()
    selectRequested = Signal()
    clearSelectionRequested = Signal()
    liquifyRequested = Signal(float, float)
    modeApplyRequested = Signal()
    modeCancelRequested = Signal()

    def __init__(self, registry: ToolRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.registry = registry
        self.groups: dict[str, ToolParamGroup] = {}
        all_names = {t.name for t in registry.all()}
        ordered = [n for n in PIPELINE_ORDER if n in all_names]
        self._order = ordered + [n for n in all_names if n not in set(ordered)]
        self._mode = "view"
        self.setStyleSheet(_qss(theme.current()))
        self.setMinimumWidth(320)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._emit_preview)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        root.addWidget(self._build_tabs(), 1)

        log_row = QHBoxLayout()
        log_title = QLabel(tr("调用记录"))
        log_title.setStyleSheet("color:#cfcfcf; font-weight:bold;")
        log_row.addWidget(log_title)
        log_row.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("status")
        log_row.addWidget(self.status)
        root.addLayout(log_row)
        self.log_view = QTextBrowser()
        self.log_view.setObjectName("logView")
        self.log_view.setFixedHeight(84)
        root.addWidget(self.log_view)

        # 区域名称水印：正中央、半透明
        self.watermark = Watermark(
            area_name("params"), self, point_size=26,
            alpha=int(theme.current()["watermark_alpha"]), color=str(theme.current()["watermark"]),
        )

    def apply_theme(self) -> None:
        self.setStyleSheet(_qss(theme.current()))
        self.watermark.set_color(
            str(theme.current()["watermark"]), int(theme.current()["watermark_alpha"])
        )

    # ---------- 分类标签 ----------
    def _build_tabs(self) -> QTabWidget:
        self.tabs = QTabWidget()
        for name, tool_names in CATEGORIES:
            page = QWidget()
            page_lay = QVBoxLayout(page)
            page_lay.setContentsMargins(0, 0, 0, 0)
            page_lay.setSpacing(6)

            inner = QWidget()
            inner_lay = QVBoxLayout(inner)
            inner_lay.setContentsMargins(2, 2, 4, 2)
            inner_lay.setSpacing(8)

            for tool_name in tool_names:
                try:
                    tool = self.registry.get(tool_name)
                except KeyError:
                    continue
                group = ToolParamGroup(tool)
                group.changed.connect(self._schedule_preview)
                self.groups[tool_name] = group
                inner_lay.addWidget(group)

            if name == "构图":
                self.crop = _CropControl()
                self.crop.start.connect(self.cropRequested)
                self.crop.apply.connect(self.modeApplyRequested)
                self.crop.cancel.connect(self.modeCancelRequested)
                inner_lay.addWidget(self.crop)
                self.select = _SelectionControl()
                self.select.select.connect(self.selectRequested)
                self.select.clear.connect(self.clearSelectionRequested)
                inner_lay.addWidget(self.select)
            if name == "特效":
                self.liquify = _LiquifyControl()
                self.liquify.start.connect(self.liquifyRequested)
                self.liquify.apply.connect(self.modeApplyRequested)
                self.liquify.cancel.connect(self.modeCancelRequested)
                inner_lay.addWidget(self.liquify)

            # 模块内的重置按钮（占满整行宽度）
            reset_btn = QPushButton(tr("重置本模块"))
            reset_btn.setMinimumHeight(30)
            reset_btn.setToolTip(tr("重置本模块"))
            reset_btn.clicked.connect(
                lambda _=False, ns=list(tool_names): self._reset_module(ns)
            )
            inner_lay.addWidget(reset_btn)

            inner_lay.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setWidget(inner)
            page_lay.addWidget(scroll)
            self.tabs.addTab(page, tr(name))
        return self.tabs

    # ---------- 预览 ----------
    def _schedule_preview(self) -> None:
        if self._mode == "view":
            self._debounce.start()

    def _emit_preview(self) -> None:
        jobs = self.active_jobs()
        self.previewChanged.emit(jobs)

    def active_jobs(self) -> list[tuple[str, dict[str, Any]]]:
        jobs: list[tuple[str, dict[str, Any]]] = []
        for name in self._order:
            group = self.groups.get(name)
            if group is not None and not group.is_default():
                jobs.append((name, group.values()))
        return jobs

    def reset_all(self) -> None:
        for group in self.groups.values():
            group.reset_defaults()
        self._debounce.stop()
        self.previewChanged.emit([])

    def _reset_module(self, names: list[str]) -> None:
        for name in names:
            group = self.groups.get(name)
            if group is not None:
                group.reset_defaults()
        self._schedule_preview()

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        if hasattr(self, "crop"):
            self.crop.set_mode(mode)
        if hasattr(self, "liquify"):
            self.liquify.set_mode(mode)

    def set_selection_active(self, active: bool) -> None:
        if hasattr(self, "select"):
            self.select.set_active(active)

    def set_busy(self, busy: bool) -> None:
        self.tabs.setEnabled(not busy)

    def log(self, text: str, color: str = "#c0a060") -> None:
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.log_view.append(f'<span style="color:{color}">{safe}</span>')
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
