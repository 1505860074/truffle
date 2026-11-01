"""对话栏：QQ/微信风格的气泡对话。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .i18n import tr
from .naming import area_name
from .watermark import Watermark


class ChatPanel(QWidget):
    submitted = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self._container = QWidget()
        self._container.setObjectName("chatContainer")
        self._messages = QVBoxLayout(self._container)
        self._messages.setContentsMargins(8, 8, 8, 8)
        self._messages.setSpacing(8)
        self._messages.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setWidget(self._container)

        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("例如：帮我把脸修瘦一点，皮肤磨光滑"))
        self.input.returnPressed.connect(self._emit)
        self.send_button = QPushButton(tr("发送"))
        self.send_button.clicked.connect(self._emit)

        row = QHBoxLayout()
        row.addWidget(self.input)
        row.addWidget(self.send_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroll, 1)
        layout.addLayout(row)

        self.watermark = Watermark(
            area_name("chat"), self.scroll.viewport(), point_size=30,
            alpha=int(theme.current()["watermark_alpha"]), color=str(theme.current()["watermark"]),
        )
        self.apply_theme()

    def apply_theme(self) -> None:
        t = theme.current()
        bg = str(t["chat_bg"])
        self.scroll.setStyleSheet(
            f"QScrollArea{{background:{bg};border:none;}} #chatContainer{{background:{bg};}}"
        )
        self.watermark.set_color(str(t["watermark"]), int(t["watermark_alpha"]))

    # ---------- 输入 ----------
    def _emit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.submitted.emit(text)

    # ---------- 消息 ----------
    def add_user(self, text: str) -> None:
        t = theme.current()
        self._bubble(text, str(t["bubble_user"]), str(t["bubble_user_fg"]), right=True)

    def add_assistant(self, text: str) -> None:
        t = theme.current()
        self._bubble(text, str(t["bubble_other"]), str(t["bubble_other_fg"]), right=False)

    def add_system(self, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"color:{theme.current()['text_dim']}; padding:2px;")
        self._messages.insertWidget(self._messages.count() - 1, label)
        self._scroll_bottom()

    def _bubble(self, text: str, bg: str, fg: str, right: bool) -> None:
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(300)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:10px; padding:8px 10px;")
        if right:
            h.addStretch(1)
            h.addWidget(label)
        else:
            h.addWidget(label)
            h.addStretch(1)
        self._messages.insertWidget(self._messages.count() - 1, wrap)
        self._scroll_bottom()

    def clear(self) -> None:
        while self._messages.count() > 1:
            item = self._messages.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _scroll_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.send_button.setEnabled(not busy)
        self.send_button.setText(tr("处理中…") if busy else tr("发送"))
