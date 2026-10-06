"""后台执行线程：把耗时的 LLM 调用与 CV 处理移出 UI 线程。"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..agent.orchestrator import Orchestrator


class AgentWorker(QThread):
    imageReady = Signal()
    replied = Signal(str)
    failed = Signal(str)

    def __init__(self, orchestrator: Orchestrator, text: str) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.text = text

    def run(self) -> None:
        try:
            reply = self.orchestrator.handle(self.text, on_image=self.imageReady.emit)
            self.replied.emit(reply)
        except Exception as exc:  # 线程内异常必须捕获后经信号回传
            self.failed.emit(str(exc))
