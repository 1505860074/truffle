"""编辑历史步骤的参数（工具 / 裁剪）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

from ..core.image_doc import Step
from ..tools.registry import ToolRegistry
from .param_panel import ToolParamGroup


class StepEditDialog(QDialog):
    def __init__(self, registry: ToolRegistry, step: Step, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("修改步骤参数")
        self.setMinimumWidth(360)
        self.step = step
        self.group: ToolParamGroup | None = None
        self._spins: dict[str, QSpinBox] = {}

        layout = QVBoxLayout(self)
        if step.kind == "tool":
            tool = registry.get(step.data["name"])
            self.group = ToolParamGroup(tool)
            self.group.set_values(step.data.get("params", {}))
            layout.addWidget(self.group)
        elif step.kind == "crop":
            x, y, w, h = step.data.get("rect", (0, 0, 0, 0))
            form = QFormLayout()
            for key, value in (("x", x), ("y", y), ("宽", w), ("高", h)):
                sp = QSpinBox()
                sp.setRange(0, 20000)
                sp.setValue(int(value))
                self._spins[key] = sp
                form.addRow(key, sp)
            layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_data(self) -> dict:
        if self.step.kind == "tool" and self.group is not None:
            return {"name": self.step.data["name"], "params": self.group.values()}
        if self.step.kind == "crop":
            rect = tuple(self._spins[k].value() for k in ("x", "y", "宽", "高"))
            return {"rect": rect}
        return dict(self.step.data)
