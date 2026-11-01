"""账号对话框：登录 / 注册（邮箱或手机号 + 密码）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from .i18n import tr


class AccountDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("账号"))
        self.setMinimumWidth(400)

        self.mode = QComboBox()
        self.mode.addItem(tr("登录"), "login")
        self.mode.addItem(tr("注册"), "register")

        self.username = QLineEdit()
        self.username.setPlaceholderText(tr("邮箱或手机号"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText(tr("密码"))

        form = QFormLayout()
        form.addRow(tr("方式"), self.mode)
        form.addRow(tr("账号"), self.username)
        form.addRow(tr("密码"), self.password)

        tip = QLabel(tr("账号用于登录与后续的社区功能，一人一个账号。"))
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#888888;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(tip)
        layout.addWidget(buttons)

    def result_credentials(self) -> tuple[str, str, str]:
        return (
            self.mode.currentData(),
            self.username.text().strip(),
            self.password.text(),
        )
