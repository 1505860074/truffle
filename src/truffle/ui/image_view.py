"""图像画布：自适应缩放显示当前图像。"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget


def bgr_to_qimage(image: np.ndarray) -> QImage:
    """OpenCV BGR ndarray → QImage（拷贝，安全）。"""
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()


class ImageView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._image: QImage | None = None
        self.setMinimumSize(400, 300)

    def set_array(self, image: np.ndarray) -> None:
        self._image = bgr_to_qimage(image)
        self.update()

    def clear(self) -> None:
        self._image = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))
        if self._image is None:
            painter.setPen(QColor("#888888"))
            painter.drawText(self.rect(), Qt.AlignCenter, "打开一张图片开始修图")
            return

        scaled = self._image.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawImage(x, y, scaled)
