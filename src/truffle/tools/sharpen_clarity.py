"""锐化 / 清晰度：边缘锐化与局部对比（通透感）。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class SharpenClarityTool(BaseTool):
    name = "sharpen_clarity"
    description = "锐化与清晰度：让画面更锐利通透。"
    parameters = [
        ToolParameter("sharpen", "锐化强度，0 无效果。", "number", 0.0, 1.0, 0.0),
        ToolParameter("clarity", "清晰度（局部对比），负数更柔、正数更通透。", "number", -1.0, 1.0, 0.0),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        sharpen: float = 0.0, clarity: float = 0.0,
    ) -> np.ndarray:
        if sharpen == 0 and clarity == 0:
            return image.copy()
        out = image
        if sharpen > 0:
            blur = cv2.GaussianBlur(out, (0, 0), 2.0)
            out = cv2.addWeighted(out, 1.0 + sharpen, blur, -sharpen, 0)
        if clarity:
            blur2 = cv2.GaussianBlur(out, (0, 0), 8.0)
            out = cv2.addWeighted(out, 1.0 + clarity * 0.8, blur2, -clarity * 0.8, 0)
        return out
