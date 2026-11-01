"""常规设置对话框：关闭行为 / 主题 / 语言。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import AppSettings
from .i18n import tr


class GeneralSettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("常规设置"))
        self.setMinimumWidth(420)

        self.project_dir = QLineEdit(settings.project_dir)
        self.project_dir.setPlaceholderText("留空 = 文档\\Truffle Projects")
        browse = QPushButton(tr("浏览…"))
        browse.clicked.connect(self._browse_project_dir)
        dir_row = QWidget()
        dir_lay = QHBoxLayout(dir_row)
        dir_lay.setContentsMargins(0, 0, 0, 0)
        dir_lay.addWidget(self.project_dir, 1)
        dir_lay.addWidget(browse)

        self.autosave = QSpinBox()
        self.autosave.setRange(0, 600)
        self.autosave.setSingleStep(30)
        self.autosave.setValue(max(0, int(settings.autosave_interval)))
        self.autosave.setSuffix(" 秒")
        self.autosave.setSpecialValueText(tr("关闭"))

        self.history_steps = QSpinBox()
        self.history_steps.setRange(0, 100)
        self.history_steps.setValue(max(0, min(100, int(settings.history_steps))))

        self.agent_history = QComboBox()
        self.agent_history.addItem(tr("一次 AI 请求算一步"), "request")
        self.agent_history.addItem(tr("每个工具算一步"), "tool")
        idx = self.agent_history.findData(settings.agent_history_mode)
        self.agent_history.setCurrentIndex(idx if idx >= 0 else 0)

        self.project_view = QComboBox()
        self.project_view.addItem(tr("卡片"), "card")
        self.project_view.addItem(tr("列表"), "list")
        idx = self.project_view.findData(settings.project_view)
        self.project_view.setCurrentIndex(idx if idx >= 0 else 0)

        self.cover_mode = QComboBox()
        for value, label in (
            ("active", tr("当前活动图")),
            ("first", tr("第一张导入图")),
            ("tiles", tr("最近 4 张拼合")),
            ("custom", tr("自定义（逐项目）")),
        ):
            self.cover_mode.addItem(label, value)
        idx = self.cover_mode.findData(settings.default_cover_mode)
        self.cover_mode.setCurrentIndex(idx if idx >= 0 else 0)

        self.theme = QComboBox()
        self.theme.addItem(tr("深色"), "dark")
        self.theme.addItem(tr("浅色"), "light")
        idx = self.theme.findData(settings.theme)
        self.theme.setCurrentIndex(idx if idx >= 0 else 0)

        self.language = QComboBox()
        self.language.addItem("中文", "zh")
        self.language.addItem("English", "en")
        idx = self.language.findData(settings.language)
        self.language.setCurrentIndex(idx if idx >= 0 else 0)

        self.update_url = QLineEdit(settings.update_url)
        self.update_url.setPlaceholderText("Gitee Releases API 或 latest.json 地址")
        self.auto_check = QCheckBox(tr("启动时自动检查更新"))
        self.auto_check.setChecked(settings.auto_check_update)
        self.file_assoc = QCheckBox(tr("关联图片文件（双击图片用 Truffle 打开）"))
        self.file_assoc.setChecked(settings.file_assoc)
        self.project_assoc = QCheckBox(tr("关联 .truffle 项目文件（双击直接打开）"))
        self.project_assoc.setChecked(settings.project_assoc)

        self.lc_app_id = QLineEdit(settings.lc_app_id)
        self.lc_app_key = QLineEdit(settings.lc_app_key)
        self.lc_server_url = QLineEdit(settings.lc_server_url)
        self.lc_server_url.setPlaceholderText("https://xxxx.api.lncldglobal.com")
        self.require_login = QCheckBox(tr("必须登录才能使用"))
        self.require_login.setChecked(settings.require_login)
        self.community_url = QLineEdit(settings.community_url)
        self.community_url.setPlaceholderText("https://...")

        form = QFormLayout()
        form.addRow(tr("默认项目目录"), dir_row)
        form.addRow(tr("自动保存间隔"), self.autosave)
        form.addRow(tr("每图历史步数"), self.history_steps)
        form.addRow(tr("AI 历史粒度"), self.agent_history)
        form.addRow(tr("项目页视图"), self.project_view)
        form.addRow(tr("默认封面方式"), self.cover_mode)
        form.addRow(tr("主题"), self.theme)
        form.addRow(tr("语言"), self.language)
        form.addRow(tr("更新地址"), self.update_url)
        form.addRow("", self.auto_check)
        form.addRow("", self.file_assoc)
        form.addRow("", self.project_assoc)
        form.addRow(tr("LeanCloud AppID"), self.lc_app_id)
        form.addRow(tr("LeanCloud AppKey"), self.lc_app_key)
        form.addRow(tr("LeanCloud 域名"), self.lc_server_url)
        form.addRow("", self.require_login)
        form.addRow(tr("社区地址"), self.community_url)

        tip = QLabel(tr("项目会自动保存；关闭主窗口会保存并回到项目页。"))
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#888888;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(tip)
        layout.addWidget(buttons)

    def _browse_project_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("选择默认项目目录"))
        if path:
            self.project_dir.setText(path)

    def result_behavior(self) -> str:
        return "exit"

    def result_project_dir(self) -> str:
        return self.project_dir.text().strip()

    def result_autosave(self) -> int:
        return int(self.autosave.value())

    def result_history_steps(self) -> int:
        return int(self.history_steps.value())

    def result_agent_history(self) -> str:
        return str(self.agent_history.currentData())

    def result_project_view(self) -> str:
        return str(self.project_view.currentData())

    def result_cover_mode(self) -> str:
        return str(self.cover_mode.currentData())

    def result_project_assoc(self) -> bool:
        return self.project_assoc.isChecked()

    def result_theme(self) -> str:
        return self.theme.currentData()

    def result_language(self) -> str:
        return self.language.currentData()

    def result_update_url(self) -> str:
        return self.update_url.text().strip()

    def result_auto_check(self) -> bool:
        return self.auto_check.isChecked()

    def result_leancloud(self) -> tuple[str, str, str]:
        return (
            self.lc_app_id.text().strip(),
            self.lc_app_key.text().strip(),
            self.lc_server_url.text().strip(),
        )

    def result_require_login(self) -> bool:
        return self.require_login.isChecked()

    def result_community_url(self) -> str:
        return self.community_url.text().strip()

    def result_file_assoc(self) -> bool:
        return self.file_assoc.isChecked()
