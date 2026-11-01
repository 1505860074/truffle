"""成套图预览与导出：风格、N×N 拼图、中心文字/头像、朋友圈导出。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..agent.style import PROFILES
from ..cv.analyzer import Analyzer
from ..tools.registry import ToolRegistry
from .i18n import tr
from .series_worker import SeriesWorker


class SeriesDialog(QDialog):
    def __init__(
        self,
        paths: list[str],
        registry: ToolRegistry,
        analyzer: Analyzer,
        style_id: str = "tangshui",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.paths = list(paths)
        self.registry = registry
        self.analyzer = analyzer
        self.worker: SeriesWorker | None = None
        self._sheet: np.ndarray | None = None
        self.setWindowTitle(tr("成套预览与导出"))
        self.resize(980, 760)

        self.style = QComboBox()
        for key, profile in PROFILES.items():
            self.style.addItem(profile.name, key)
        index = self.style.findData(style_id)
        self.style.setCurrentIndex(index if index >= 0 else 0)

        self.columns = QSpinBox()
        self.columns.setRange(1, 9)
        self.columns.setValue(3)
        self.columns.setPrefix(tr("每行 "))

        self.consistency = QSpinBox()
        self.consistency.setRange(0, 100)
        self.consistency.setValue(80)
        self.consistency.setSuffix(" %")

        self.center_text = QLineEdit()
        self.center_text.setPlaceholderText(tr("拼图中心文字（可选）"))
        self.avatar = QLineEdit()
        avatar_btn = QPushButton(tr("选择头像…"))
        avatar_btn.clicked.connect(self._pick_avatar)
        avatar_row = QWidget()
        avatar_lay = QHBoxLayout(avatar_row)
        avatar_lay.setContentsMargins(0, 0, 0, 0)
        avatar_lay.addWidget(self.avatar, 1)
        avatar_lay.addWidget(avatar_btn)

        self.out_dir = QLineEdit()
        out_btn = QPushButton(tr("选择文件夹…"))
        out_btn.clicked.connect(self._pick_out)
        out_row = QWidget()
        out_lay = QHBoxLayout(out_row)
        out_lay.setContentsMargins(0, 0, 0, 0)
        out_lay.addWidget(self.out_dir, 1)
        out_lay.addWidget(out_btn)

        self.fmt = QComboBox()
        self.fmt.addItem("JPEG", ".jpg")
        self.fmt.addItem("PNG", ".png")
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(92)
        self.long_side = QSpinBox()
        self.long_side.setRange(0, 6000)
        self.long_side.setSingleStep(120)
        self.long_side.setValue(1080)
        self.long_side.setSuffix(" px")

        form = QFormLayout()
        form.addRow(tr("风格"), self.style)
        form.addRow(tr("拼图布局"), self.columns)
        form.addRow(tr("风格一致性"), self.consistency)
        form.addRow(tr("中心文字"), self.center_text)
        form.addRow(tr("中心头像"), avatar_row)
        form.addRow(tr("导出目录"), out_row)
        form.addRow(tr("格式"), self.fmt)
        form.addRow(tr("质量"), self.quality)
        form.addRow(tr("长边"), self.long_side)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.preview = QLabel(tr("点击「生成预览」查看成套效果。"))
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(420)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.preview)

        self.generate_btn = QPushButton(tr("生成预览"))
        self.generate_btn.clicked.connect(self._generate)
        self.export_btn = QPushButton(tr("生成并导出"))
        self.export_btn.clicked.connect(self._export)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        action_row = QHBoxLayout()
        action_row.addWidget(self.generate_btn)
        action_row.addWidget(self.export_btn)
        action_row.addStretch(1)
        action_row.addWidget(buttons)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(tr("共 ") + str(len(self.paths)) + tr(" 张图片")))
        root.addLayout(form)
        root.addWidget(self.progress)
        root.addWidget(scroll, 1)
        root.addLayout(action_row)

    def _pick_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择头像"), "", "图片 (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self.avatar.setText(path)

    def _pick_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("选择导出目录"))
        if folder:
            self.out_dir.setText(folder)

    def _generate(self) -> None:
        self._start(False)

    def _export(self) -> None:
        if not self.out_dir.text().strip():
            QMessageBox.information(self, tr("导出"), tr("请先选择导出目录。"))
            return
        self._start(True)

    def _start(self, export: bool) -> None:
        if not self.paths:
            QMessageBox.information(self, tr("成套图"), tr("文件库里没有图片。"))
            return
        if self.worker is not None and self.worker.isRunning():
            return
        self.generate_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setMaximum(len(self.paths))
        self.worker = SeriesWorker(
            self.paths,
            self.registry,
            self.analyzer,
            str(self.style.currentData()),
            consistency=self.consistency.value() / 100.0,
            columns=self.columns.value(),
            out_dir=self.out_dir.text().strip() if export else "",
            ext=str(self.fmt.currentData()),
            quality=self.quality.value(),
            long_side=self.long_side.value(),
            center_text=self.center_text.text().strip(),
            avatar_path=self.avatar.text().strip(),
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.previewReady.connect(self._on_preview)
        self.worker.exported.connect(self._on_exported)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(done)
        self.progress.setFormat(f"{done}/{total}")

    def _on_preview(self, image: np.ndarray) -> None:
        self._sheet = image
        rgb = image[..., ::-1].copy()
        h, w = rgb.shape[:2]
        qimage = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(qimage)
        if pix.width() > 900:
            pix = pix.scaledToWidth(900, Qt.SmoothTransformation)
        self.preview.setPixmap(pix)

    def _on_exported(self, paths) -> None:
        QMessageBox.information(self, tr("导出完成"), tr("已导出 ") + str(len(paths)) + tr(" 张图片。"))

    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, tr("成套图"), message)

    def _on_finished(self) -> None:
        self.generate_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
