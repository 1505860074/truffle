"""降噪：边缘保留的双边/中值降噪。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class NoiseReductionTool(BaseTool):
    name = "noise_reduction"
    description = "降噪：减少高感噪点与色噪，尽量保留边缘细节。"
    parameters = [
        ToolParameter("strength", "降噪强度，0 无效果。", "number", 0.0, 1.0, 0.35),
        ToolParameter("color", "色噪抑制强度，0~1。", "number", 0.0, 1.0, 0.3),
    ]

    def apply(
        self,
        image: np.ndarray,
        ctx: ToolContext,
        strength: float = 0.35,
        color: float = 0.3,
    ) -> np.ndarray:
        if strength <= 0 and color <= 0:
            return image.copy()
        out = image
        if strength > 0:
            d = 5 + int(4 * strength)
            sigma = 18.0 + 42.0 * strength
            out = cv2.bilateralFilter(out, d=d, sigmaColor=sigma, sigmaSpace=sigma)
        if color > 0:
            lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
            lab[..., 1] = cv2.GaussianBlur(lab[..., 1], (0, 0), 1.0 + color * 2.0)
            lab[..., 2] = cv2.GaussianBlur(lab[..., 2], (0, 0), 1.0 + color * 2.0)
            out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        return np.clip(out, 0, 255).astype(np.uint8)
