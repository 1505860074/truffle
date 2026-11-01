"""项目级一键风格：后台逐图求解并写回 .truffle。"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..agent.series import apply_style_to_project
from ..agent.style import resolve_style
from ..cv.analyzer import Analyzer
from ..tools.registry import ToolRegistry


class ProjectStyleWorker(QThread):
    progress = Signal(int, int)
    finishedOk = Signal(int)
    failed = Signal(str)

    def __init__(
        self,
        project,
        registry: ToolRegistry,
        analyzer: Analyzer,
        style_id: str,
        *,
        consistency: float = 0.8,
        history_steps: int = 20,
        history_mode: str = "request",
    ) -> None:
        super().__init__()
        self.project = project
        self.registry = registry
        self.analyzer = analyzer
        self.style_id = style_id
        self.consistency = consistency
        self.history_steps = history_steps
        self.history_mode = history_mode

    def run(self) -> None:
        try:
            profile = resolve_style(self.style_id)
            count = apply_style_to_project(
                self.project,
                self.registry,
                self.analyzer,
                profile,
                consistency=self.consistency,
                history_steps=self.history_steps,
                history_mode=self.history_mode,
                progress=self.progress.emit,
            )
            self.finishedOk.emit(count)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
