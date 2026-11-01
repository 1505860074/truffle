"""美白：在皮肤区域内提亮肤色、去黄，并保持通透（不死白）。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import refine_mask
from .base import BaseTool, ToolContext, ToolParameter


class WhitenTool(BaseTool):
    name = "whiten"
    description = "美白提亮：让皮肤更白净透亮、减轻黄气，保留高光与肤色层次，仅作用于皮肤。"
    parameters = [
        ToolParameter("strength", "美白强度，0 无效果。日常建议 0.3~0.5。", "number", 0.0, 1.0, 0.4),
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.4) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        mask = analysis.skin_mask
        if mask is None:
            return image.copy()
        mask = refine_mask(image, mask, radius=8)

        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
        L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
        # 提亮（渐进、保护高光）
        L += (255.0 - L) * (0.38 * strength)
        # 去黄（b 向中性收敛），轻微收红避免暗沉
        b += (128.0 - b) * (0.30 * strength)
        a += (128.0 - a) * (0.06 * strength)
        # 通透：L 轻微 S 曲线增加层次
        L = 127.5 + (L - 127.5) * (1.0 + 0.12 * strength)

        whitened = cv2.cvtColor(
            np.clip(cv2.merge([L, a, b]), 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR
        )
        alpha = (mask.astype(np.float32) / 255.0)[..., None]
        out = image.astype(np.float32) * (1 - alpha) + whitened.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
