"""设置对话框：配置 OpenAI 兼容的大模型接口。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..config import LLMSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: LLMSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)

        self.base_url = QLineEdit(settings.base_url)
        self.api_key = QLineEdit(settings.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.model = QLineEdit(settings.model)
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 300)
        self.timeout.setValue(settings.timeout)

        form = QFormLayout()
        form.addRow("接口地址 (base_url)", self.base_url)
        form.addRow("API Key", self.api_key)
        form.addRow("模型名称 (model)", self.model)
        form.addRow("超时（秒）", self.timeout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def result_settings(self) -> LLMSettings:
        return LLMSettings(
            base_url=self.base_url.text().strip(),
            api_key=self.api_key.text().strip(),
            model=self.model.text().strip() or "gpt-4o-mini",
            timeout=self.timeout.value(),
        )
