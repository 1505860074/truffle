"""对话面板：展示对话记录并收集用户输入。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class ChatPanel(QWidget):
    submitted = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        self.transcript.setStyleSheet("QTextBrowser { background: #181818; color: #e6e6e6; }")

        self.input = QLineEdit()
        self.input.setPlaceholderText("例如：帮我把脸修瘦一点，皮肤磨光滑")
        self.input.returnPressed.connect(self._emit)

        self.send_button = QPushButton("发送")
        self.send_button.clicked.connect(self._emit)

        row = QHBoxLayout()
        row.addWidget(self.input)
        row.addWidget(self.send_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.transcript)
        layout.addLayout(row)

    def _emit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.submitted.emit(text)

    def add_user(self, text: str) -> None:
        self._append("你", text, "#7ec8ff")

    def add_assistant(self, text: str) -> None:
        self._append("Truffle", text, "#9be29b")

    def add_system(self, text: str) -> None:
        self._append("系统", text, "#c0a060")

    def set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.send_button.setEnabled(not busy)
        self.send_button.setText("处理中…" if busy else "发送")

    def _append(self, who: str, text: str, color: str) -> None:
        safe = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        ).replace("\n", "<br>")
        self.transcript.append(
            f'<p style="margin:6px 0;"><b style="color:{color}">{who}：</b>{safe}</p>'
        )
        self.transcript.verticalScrollBar().setValue(
            self.transcript.verticalScrollBar().maximum()
        )
