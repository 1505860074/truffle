"""美白：在皮肤区域内提亮肤色、轻微降低黄气。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class WhitenTool(BaseTool):
    name = "whiten"
    description = "美白提亮：让皮肤更白净透亮，仅作用于皮肤区域。"
    parameters = [
        ToolParameter(
            "strength",
            "美白强度，0 无效果，1 最强。日常建议 0.3~0.5。",
            "number",
            minimum=0.0,
            maximum=1.0,
            default=0.4,
        )
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.4) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        mask = analysis.skin_mask
        if mask is None:
            return image.copy()

        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
        L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]

        # 提亮：向白色靠拢；同时轻微降黄（b 通道向 128 收敛）
        L += (255.0 - L) * (0.40 * strength)
        b += (128.0 - b) * (0.20 * strength)

        lab_adjusted = cv2.merge([L, a, b])
        lab_adjusted = np.clip(lab_adjusted, 0, 255).astype(np.uint8)
        brightened = cv2.cvtColor(lab_adjusted, cv2.COLOR_LAB2BGR)

        alpha = (mask.astype(np.float32) / 255.0)[..., None]
        out = image.astype(np.float32) * (1 - alpha) + brightened.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
