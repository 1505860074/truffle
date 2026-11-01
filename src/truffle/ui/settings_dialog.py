"""设置对话框：配置 OpenAI 兼容的大模型接口。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..config import LLMSettings
from .i18n import tr


class SettingsDialog(QDialog):
    def __init__(self, settings: LLMSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("设置"))
        self.setMinimumWidth(420)

        self.base_url = QLineEdit(settings.base_url)
        self.base_url.setPlaceholderText(tr("例如：https://api.deepseek.com/v1"))
        self.api_key = QLineEdit(settings.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText(tr("在此粘贴你的密钥"))
        self.model = QLineEdit(settings.model)
        self.model.setPlaceholderText(tr("例如：deepseek-chat"))
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 300)
        self.timeout.setValue(settings.timeout)

        self.vision = QCheckBox(tr("让 AI 看图（多模态，需模型支持视觉）"))
        self.vision.setChecked(settings.vision)
        self.context = QLineEdit(settings.context)
        self.context.setPlaceholderText(tr("例如：我是女生，喜欢自然清透、不夸张的风格"))

        form = QFormLayout()
        form.addRow(tr("接口地址"), self.base_url)
        form.addRow(tr("API 密钥"), self.api_key)
        form.addRow(tr("模型名称"), self.model)
        form.addRow(tr("超时（秒）"), self.timeout)
        form.addRow(tr("核心上下文"), self.context)
        form.addRow("", self.vision)

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
            vision=self.vision.isChecked(),
            context=self.context.text().strip(),
        )
