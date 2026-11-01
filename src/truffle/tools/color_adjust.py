"""调色：亮度 / 对比度 / 饱和度（最基础的全局调色）。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class ColorAdjustTool(BaseTool):
    name = "color_adjust"
    description = "基础调色：调整画面亮度、对比度与饱和度。"
    parameters = [
        ToolParameter("brightness", "亮度，负数变暗、正数变亮。", "number", -1.0, 1.0, 0.0),
        ToolParameter("contrast", "对比度，负数更灰、正数更强烈。", "number", -1.0, 1.0, 0.0),
        ToolParameter("saturation", "饱和度，负数更淡、正数更艳。", "number", -1.0, 1.0, 0.0),
    ]

    def apply(
        self,
        image: np.ndarray,
        ctx: ToolContext,
        brightness: float = 0.0,
        contrast: float = 0.0,
        saturation: float = 0.0,
    ) -> np.ndarray:
        if brightness == 0 and contrast == 0 and saturation == 0:
            return image.copy()
        out = image.astype(np.float32)
        if brightness:
            out += brightness * 70.0
        if contrast:
            out = (out - 127.5) * (1.0 + contrast) + 127.5
        out = np.clip(out, 0, 255).astype(np.uint8)
        if saturation:
            hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + saturation), 0, 255)
            out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        return out
