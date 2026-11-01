"""工具渲染管线：把「底图 + 一组 (工具, 参数)」按顺序渲染成新图。

预览与导出共用同一条管线，保证「所见即所得」：
- 底图的人脸/姿态/前景只检测一次并钉住（`ToolContext(pin=...)`），后续工具复用；
- 顺序由调用方给出（见 `ui/param_panel.PIPELINE_ORDER`），保证预览与全分辨率导出一致。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..cv.analyzer import Analyzer
from .base import ToolContext
from .registry import ToolRegistry

_POSE_TOOLS = {"body_slim", "leg_lengthen"}


def render_pipeline(
    registry: ToolRegistry,
    analyzer: Analyzer,
    base: np.ndarray,
    jobs: list[tuple[str, dict[str, Any]]],
) -> np.ndarray:
    if not jobs:
        return base.copy()

    names = {name for name, _ in jobs}
    analysis = analyzer.analyze(base)
    pose = analyzer.pose(base) if names & _POSE_TOOLS else None
    foreground = analyzer.foreground(base) if "background_blur" in names else None
    pin = {"analysis": analysis, "pose": pose, "foreground": foreground}

    ctx = ToolContext(analyzer, pin=pin)
    image = base
    for name, params in jobs:
        image = registry.execute(name, image, ctx, params)
    return image
