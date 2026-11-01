"""磨皮：频率分离——平滑肤色（低频）同时保留皮肤纹理（高频），只作用于皮肤。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import refine_mask
from .base import BaseTool, ToolContext, ToolParameter


class SkinSmoothTool(BaseTool):
    name = "skin_smooth"
    description = "磨皮：让皮肤更光滑细腻，保留皮肤质感与五官细节，只作用于皮肤区域。"
    parameters = [
        ToolParameter("strength", "磨皮强度，0 无效果。日常建议 0.4~0.6。", "number", 0.0, 1.0, 0.5),
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.5) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        mask = analysis.skin_mask
        if mask is None:
            return image.copy()
        mask = refine_mask(image, mask, radius=8)
        alpha = (mask.astype(np.float32) / 255.0 * strength)[..., None]

        # 频率分离：低频=肤色，高频=纹理
        low = cv2.GaussianBlur(image, (0, 0), 6.0)
        high = image.astype(np.float32) - low.astype(np.float32)
        sigma = 20.0 + 60.0 * strength
        low_s = cv2.bilateralFilter(low, d=9, sigmaColor=sigma, sigmaSpace=sigma)
        high_r = high * (1.0 - 0.55 * strength)  # 轻微减弱毛孔/细纹，保留质感
        smoothed = np.clip(low_s.astype(np.float32) + high_r, 0, 255).astype(np.uint8)

        out = image.astype(np.float32) * (1 - alpha) + smoothed.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
