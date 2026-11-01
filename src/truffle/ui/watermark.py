"""区域水印：在功能区正中央以半透明大字显示该区名称。

用法：
    label = Watermark(AREA_NAMES["chat"], self.transcript.viewport())

它是覆盖在目标控件之上的子控件，自动跟随父控件尺寸、不接收鼠标事件，
因此不会挡住下面的交互。名称取自 `ui/naming.py` 的命名规则。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget


class Watermark(QWidget):
    def __init__(
        self,
        text: str,
        parent: QWidget,
        *,
        point_size: int = 34,
        alpha: int = 34,
        color: str = "#e7c87e",
        spacing: int = 6,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._point_size = point_size
        self._spacing = spacing
        self._color = QColor(color)
        self._color.setAlpha(alpha)

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)

        parent.installEventFilter(self)
        self._sync_geometry()

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()

    def set_color(self, color: str, alpha: int) -> None:
        self._color = QColor(color)
        self._color.setAlpha(alpha)
        self.update()

    def _sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())
            self.raise_()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt 命名)
        if obj is self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Show):
            self._sync_geometry()
        return super().eventFilter(obj, event)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = QFont()
        font.setPointSize(self._point_size)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, self._spacing)
        painter.setFont(font)
        painter.setPen(self._color)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)
