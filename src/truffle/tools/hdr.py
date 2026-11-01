"""HDR 影调：CLAHE 找回亮暗细节 + 局部对比，画面更通透立体。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class HdrTool(BaseTool):
    name = "hdr"
    description = "HDR 影调：找回亮部与暗部细节，增加通透与立体感。"
    parameters = [
        ToolParameter("strength", "影调强度，0 无效果。", "number", 0.0, 1.0, 0.5),
        ToolParameter("local_contrast", "局部对比，越大越立体。", "number", 0.0, 1.0, 0.3),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        strength: float = 0.5, local_contrast: float = 0.3,
    ) -> np.ndarray:
        if strength <= 0 and local_contrast <= 0:
            return image.copy()
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        L = lab[..., 0]
        if strength > 0:
            clahe = cv2.createCLAHE(clipLimit=1.5 + strength * 3.0, tileGridSize=(8, 8))
            L = clahe.apply(L)
        if local_contrast > 0:
            blur = cv2.GaussianBlur(L, (0, 0), 8.0)
            L = cv2.addWeighted(L, 1.0 + local_contrast * 0.6, blur, -local_contrast * 0.6, 0)
        lab[..., 0] = np.clip(L, 0, 255).astype(np.uint8)
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
