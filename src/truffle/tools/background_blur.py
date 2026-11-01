"""背景虚化：识别人像前景，虚化背景以突出主体（边缘用导向滤波贴合，不穿帮）。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import refine_mask
from .base import BaseTool, ToolContext, ToolParameter


class BackgroundBlurTool(BaseTool):
    name = "background_blur"
    description = "背景虚化：自动识别主体，虚化背景，突出人物，边缘干净。"
    parameters = [
        ToolParameter("strength", "虚化强度，0 无效果。", "number", 0.0, 1.0, 0.5),
        ToolParameter("feather", "边缘羽化，越大过渡越自然。", "number", 0.0, 1.0, 0.4),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        strength: float = 0.5, feather: float = 0.4,
    ) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        fg = ctx.foreground(image)
        if fg is None:
            return image.copy()
        fg = refine_mask(image, fg, radius=10)  # 边缘贴合人物轮廓

        sigma = 1.0 + strength * 24.0
        blurred = cv2.GaussianBlur(image, (0, 0), sigma)
        alpha = fg.astype(np.float32) / 255.0
        if feather > 0:
            k = int(2 * round(feather * 12) + 1)
            alpha = cv2.GaussianBlur(alpha, (k, k), 0)
        alpha = alpha[..., None]
        out = image.astype(np.float32) * alpha + blurred.astype(np.float32) * (1 - alpha)
        return np.clip(out, 0, 255).astype(np.uint8)
