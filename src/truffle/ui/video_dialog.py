"""视频修饰对话框：选择输入/输出视频与要套用的工具参数。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..tools.registry import ToolRegistry
from .i18n import tr
from .param_panel import ToolParamGroup
from .tool_labels import tool_label

VIDEO_FILTER = "视频 (*.mp4 *.avi *.mov *.mkv *.webm)"


class VideoDialog(QDialog):
    def __init__(self, registry: ToolRegistry, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("视频修饰"))
        self.setMinimumWidth(460)
        self.registry = registry
        self._group: ToolParamGroup | None = None

        self.input = QLineEdit()
        in_btn = QPushButton(tr("浏览…"))
        in_btn.clicked.connect(lambda: self._browse(self.input, True))
        in_row = QHBoxLayout()
        in_row.addWidget(self.input, 1)
        in_row.addWidget(in_btn)

        self.output = QLineEdit()
        out_btn = QPushButton(tr("浏览…"))
        out_btn.clicked.connect(lambda: self._browse(self.output, False))
        out_row = QHBoxLayout()
        out_row.addWidget(self.output, 1)
        out_row.addWidget(out_btn)

        self.tool = QComboBox()
        for t in registry.all():
            self.tool.addItem(tool_label(t.name), t.name)
        self.tool.currentIndexChanged.connect(self._rebuild_group)

        self.max_side = QSpinBox()
        self.max_side.setRange(0, 4000)
        self.max_side.setValue(1280)
        self.max_side.setToolTip(tr("处理的最长边上限（0=原始尺寸，越小越快）"))

        form = QFormLayout()
        form.addRow(tr("输入视频"), in_row)
        form.addRow(tr("输出视频"), out_row)
        form.addRow(tr("工具"), self.tool)
        form.addRow(tr("最长边上限"), self.max_side)

        self.group_host = QVBoxLayout()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("开始"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(self.group_host)
        layout.addWidget(buttons)
        self._rebuild_group()

    def _rebuild_group(self) -> None:
        if self._group is not None:
            self._group.setParent(None)
        name = self.tool.currentData()
        self._group = ToolParamGroup(self.registry.get(name))
        self.group_host.addWidget(self._group)

    def _browse(self, target: QLineEdit, is_input: bool) -> None:
        if is_input:
            path, _ = QFileDialog.getOpenFileName(self, tr("选择视频"), "", VIDEO_FILTER)
        else:
            path, _ = QFileDialog.getSaveFileName(self, tr("输出视频"), "truffle_output.mp4", "视频 (*.mp4)")
        if path:
            target.setText(path)

    def result_input(self) -> str:
        return self.input.text().strip()

    def result_output(self) -> str:
        return self.output.text().strip()

    def result_jobs(self) -> list[tuple[str, dict]]:
        name = self.tool.currentData()
        return [(name, self._group.values())] if self._group is not None else []

    def result_max_side(self) -> int:
        return self.max_side.value()
