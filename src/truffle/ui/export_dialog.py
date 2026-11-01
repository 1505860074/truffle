"""导出对话框：格式 / 质量 / 保留 EXIF。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
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

from .i18n import tr


class ExportDialog(QDialog):
    def __init__(self, default_name: str = "truffle_output.png", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("导出"))
        self.setMinimumWidth(440)

        self.path = QLineEdit(default_name)
        browse = QPushButton(tr("浏览…"))
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path, 1)
        path_row.addWidget(browse)

        self.fmt = QComboBox()
        for label, ext in (("PNG", ".png"), ("JPEG", ".jpg"), ("WebP", ".webp")):
            self.fmt.addItem(label, ext)
        self.fmt.currentIndexChanged.connect(self._sync_ext)

        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(92)

        self.keep_exif = QCheckBox(tr("保留 EXIF（仅 JPEG）"))
        self.keep_exif.setChecked(True)

        form = QFormLayout()
        form.addRow(tr("保存到"), path_row)
        form.addRow(tr("格式"), self.fmt)
        form.addRow(tr("质量"), self.quality)
        form.addRow("", self.keep_exif)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _sync_ext(self) -> None:
        ext = self.fmt.currentData()
        p = Path(self.path.text().strip() or "truffle_output")
        self.path.setText(str(p.with_suffix(ext)))

    def _browse(self) -> None:
        ext = self.fmt.currentData()
        pattern = {".png": "PNG (*.png)", ".jpg": "JPEG (*.jpg)", ".webp": "WebP (*.webp)"}[ext]
        chosen, _ = QFileDialog.getSaveFileName(self, tr("导出"), self.path.text(), pattern)
        if chosen:
            self.path.setText(chosen)

    def result_path(self) -> str:
        p = Path(self.path.text().strip() or "truffle_output")
        ext = self.fmt.currentData()
        if p.suffix.lower() != ext:
            p = p.with_suffix(ext)
        return str(p)

    def result_quality(self) -> int:
        return self.quality.value()

    def result_keep_exif(self) -> bool:
        return self.keep_exif.isChecked()
