"""HSL：整体色相 / 饱和度 / 明度。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class HslTool(BaseTool):
    name = "hsl"
    description = "HSL 调色：整体调整色相、饱和度与明度。"
    parameters = [
        ToolParameter("hue", "色相偏移，-1~1 对应约 -180°~180°。", "number", -1.0, 1.0, 0.0),
        ToolParameter("saturation", "饱和度，负数更淡、正数更艳。", "number", -1.0, 1.0, 0.0),
        ToolParameter("lightness", "明度，负数更暗、正数更亮。", "number", -1.0, 1.0, 0.0),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        hue: float = 0.0, saturation: float = 0.0, lightness: float = 0.0,
    ) -> np.ndarray:
        if hue == 0 and saturation == 0 and lightness == 0:
            return image.copy()
        hls = cv2.cvtColor(image, cv2.COLOR_BGR2HLS).astype(np.float32)
        H, L, S = hls[..., 0], hls[..., 1], hls[..., 2]
        if hue:
            H = (H + hue * 180.0) % 180.0
        if saturation:
            S = np.clip(S * (1.0 + saturation), 0, 255)
        if lightness:
            if lightness > 0:
                L = L + (255.0 - L) * lightness
            else:
                L = L * (1.0 + lightness)
        merged = np.clip(cv2.merge([H, L, S]), 0, 255).astype(np.uint8)
        return cv2.cvtColor(merged, cv2.COLOR_HLS2BGR)
