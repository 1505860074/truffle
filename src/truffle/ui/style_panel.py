"""一键修图：选风格 → 本地求解参数 → 应用到当前图或整个项目。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from ..agent.style import PROFILES
from . import theme
from .i18n import tr


class StylePanel(QWidget):
    applyCurrent = Signal(str)
    applyAll = Signal(str, float)
    autoStyle = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._style_id = "tangshui"
        self._buttons: dict[str, QPushButton] = {}

        title = QLabel(tr("一键修图"))
        title.setStyleSheet("font-size:16px;font-weight:bold;")
        tip = QLabel(tr("选一个风格，参数由本地策略按图片自动计算。"))
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#8b8b8b;")

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (style_id, profile) in enumerate(PROFILES.items()):
            button = QPushButton(tr(profile.name))
            button.setCheckable(True)
            button.setToolTip(profile.description)
            button.clicked.connect(lambda checked=False, sid=style_id: self._select(sid))
            grid.addWidget(button, i // 2, i % 2)
            self._buttons[style_id] = button

        self.current_btn = QPushButton(tr("应用到当前图片"))
        self.current_btn.clicked.connect(lambda: self.applyCurrent.emit(self._style_id))
        self.all_btn = QPushButton(tr("一键应用到全部图片"))
        self.all_btn.clicked.connect(
            lambda: self.applyAll.emit(self._style_id, self.consistency.value() / 100.0)
        )
        self.auto_btn = QPushButton(tr("自动选择风格"))
        self.auto_btn.clicked.connect(self.autoStyle.emit)

        self.consistency = QSlider(Qt.Horizontal)
        self.consistency.setRange(0, 100)
        self.consistency.setValue(80)
        consistency_row = QWidget()
        from PySide6.QtWidgets import QHBoxLayout

        consistency_lay = QHBoxLayout(consistency_row)
        consistency_lay.setContentsMargins(0, 0, 0, 0)
        consistency_lay.addWidget(QLabel(tr("成套一致性")))
        consistency_lay.addWidget(self.consistency, 1)

        self.status = QLabel(tr("就绪"))
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#8b8b8b;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(tip)
        layout.addLayout(grid)
        layout.addWidget(self.current_btn)
        layout.addWidget(self.all_btn)
        layout.addWidget(self.auto_btn)
        layout.addWidget(consistency_row)
        layout.addWidget(self.status)
        layout.addStretch(1)
        self._select(self._style_id)

    def _select(self, style_id: str) -> None:
        self._style_id = style_id
        for sid, button in self._buttons.items():
            button.setChecked(sid == style_id)
        profile = PROFILES.get(style_id)
        if profile is not None:
            self.status.setText(profile.name + " · " + profile.description)

    def current_style(self) -> str:
        return self._style_id

    def select_style(self, style_id: str) -> None:
        self._select(style_id)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_busy(self, busy: bool) -> None:
        for button in self._buttons.values():
            button.setEnabled(not busy)
        self.current_btn.setEnabled(not busy)
        self.all_btn.setEnabled(not busy)
        self.auto_btn.setEnabled(not busy)

    def apply_theme(self) -> None:
        t = theme.current()
        self.setStyleSheet(
            f"QWidget{{background:{t['panel_bg']};color:{t['text']};}}"
            f"QPushButton{{background:{t['button']};color:{t['button_text']};"
            f"border:1px solid {t['border']};border-radius:6px;padding:6px;}}"
            f"QPushButton:checked{{background:{t['accent_bg']};color:{t['accent']};"
            f"border:1px solid {t['accent']};}}"
            f"QPushButton:hover{{border:1px solid {t['accent']};}}"
        )
