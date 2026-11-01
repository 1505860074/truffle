"""批量套用风格对话框：以当前图为模板，把风格套用到文件库的其它图片。"""

from __future__ import annotations

from PySide6.QtWidgets import (
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
)

from .i18n import tr


class BatchDialog(QDialog):
    def __init__(self, template_name: str, library_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("批量处理"))
        self.setMinimumWidth(460)

        info = QLabel(
            tr("模板：") + template_name + "\n" + tr("文件库：") + f"{library_count}" + tr(" 张")
        )
        info.setWordWrap(True)

        self.mode = QComboBox()
        self.mode.addItem(tr("套用模板风格"), "template")
        self.mode.addItem(tr("自动调色"), "auto")

        self.out_dir = QLineEdit()
        browse = QPushButton(tr("选择文件夹…"))
        browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.out_dir, 1)
        dir_row.addWidget(browse)

        self.fmt = QComboBox()
        self.fmt.addItem("PNG", ".png")
        self.fmt.addItem("JPEG", ".jpg")
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(92)

        form = QFormLayout()
        form.addRow(tr("模式"), self.mode)
        form.addRow(tr("导出到"), dir_row)
        form.addRow(tr("格式"), self.fmt)
        form.addRow(tr("质量"), self.quality)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("开始"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("选择导出文件夹"))
        if folder:
            self.out_dir.setText(folder)

    def result_mode(self) -> str:
        return self.mode.currentData()

    def result_out_dir(self) -> str:
        return self.out_dir.text().strip()

    def result_format(self) -> str:
        return self.fmt.currentData()

    def result_quality(self) -> int:
        return self.quality.value()
