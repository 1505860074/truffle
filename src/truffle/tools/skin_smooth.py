"""磨皮：在皮肤区域内平滑皮肤、淡化毛孔与细纹。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class SkinSmoothTool(BaseTool):
    name = "skin_smooth"
    description = "磨皮：让皮肤更光滑细腻，淡化毛孔和细纹，只作用于皮肤区域，不模糊五官。"
    parameters = [
        ToolParameter(
            "strength",
            "磨皮强度，0 表示无效果，1 表示最强。日常人像建议 0.4~0.6。",
            "number",
            minimum=0.0,
            maximum=1.0,
            default=0.5,
        )
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.5) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        mask = analysis.skin_mask
        if mask is None:
            return image.copy()

        sigma = 30 + 90 * strength
        smoothed = cv2.bilateralFilter(image, d=9, sigmaColor=sigma, sigmaSpace=sigma)

        alpha = (mask.astype(np.float32) / 255.0 * strength)[..., None]
        out = image.astype(np.float32) * (1 - alpha) + smoothed.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
