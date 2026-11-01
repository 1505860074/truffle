"""单图一键风格后台任务：测量 → 求解 → 渲染，UI 保持响应。"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QThread, Signal

from ..agent.critic import evaluate
from ..agent.solver import ParamSolver
from ..agent.style import resolve_style
from ..cv.analyzer import Analyzer
from ..cv.metrics import measure
from ..tools.pipeline import render_pipeline
from ..tools.registry import ToolRegistry


class StyleApplyWorker(QThread):
    status = Signal(str)
    finishedOk = Signal(object, object, object)  # styled image, jobs, critique
    failed = Signal(str)

    def __init__(
        self,
        image: np.ndarray,
        registry: ToolRegistry,
        analyzer: Analyzer,
        style_id: str,
    ) -> None:
        super().__init__()
        self.image = np.ascontiguousarray(image)
        self.registry = registry
        self.analyzer = analyzer
        self.style_id = style_id

    def run(self) -> None:
        try:
            profile = resolve_style(self.style_id)
            self.status.emit("正在分析画面…")
            before = measure(self.image, self.analyzer)
            self.status.emit("正在计算风格参数…")
            solver = ParamSolver(self.registry, self.analyzer)
            result = solver.solve(self.image, profile, before)
            self.status.emit("正在应用到全分辨率…")
            styled = render_pipeline(self.registry, self.analyzer, self.image, result.jobs) if result.jobs else self.image
            after = measure(styled, self.analyzer)
            critique = evaluate(before, after, profile, result.jobs, result.naturalness)
            self.finishedOk.emit(styled, result.jobs, critique.to_dict())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
