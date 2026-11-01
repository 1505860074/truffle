"""扭曲：参数化的旋转/收拢/膨胀/拉伸形变（可被 AI 调用，也出现在参数栏）。"""

from __future__ import annotations

import numpy as np

from ..cv.warp import distort as warp_distort
from .base import BaseTool, ToolContext, ToolParameter


class DistortTool(BaseTool):
    name = "distort"
    description = "扭曲形变：对指定中心与半径做旋转、收拢、膨胀或单向拉伸。"
    parameters = [
        ToolParameter(
            "mode", "扭曲方式。", "string", default="twirl",
            enum=["twirl", "pinch", "bulge", "stretch_h", "stretch_v"],
        ),
        ToolParameter("strength", "强度，负数反向。", "number", -1.0, 1.0, 0.4),
        ToolParameter("center_x", "中心横向位置（0~1，相对宽度）。", "number", 0.0, 1.0, 0.5),
        ToolParameter("center_y", "中心纵向位置（0~1，相对高度）。", "number", 0.0, 1.0, 0.5),
        ToolParameter("radius", "作用半径（相对短边，0~1）。", "number", 0.1, 1.0, 0.5),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        mode: str = "twirl", strength: float = 0.4,
        center_x: float = 0.5, center_y: float = 0.5, radius: float = 0.5,
    ) -> np.ndarray:
        if strength == 0:
            return image.copy()
        h, w = image.shape[:2]
        cx, cy = center_x * w, center_y * h
        r = radius * min(h, w)
        return warp_distort(image, mode, strength, cx, cy, r)
