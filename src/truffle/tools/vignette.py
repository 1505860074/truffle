"""暗角：四周压暗、突出主体。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class VignetteTool(BaseTool):
    name = "vignette"
    description = "暗角：让画面四周变暗，突出中间主体。"
    parameters = [
        ToolParameter("amount", "暗角强度，0 无效果。", "number", 0.0, 1.0, 0.5),
        ToolParameter("softness", "过渡柔和度，越大越自然。", "number", 0.1, 1.0, 0.6),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        amount: float = 0.5, softness: float = 0.6,
    ) -> np.ndarray:
        if amount <= 0:
            return image.copy()
        h, w = image.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = w / 2.0, h / 2.0
        d = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / np.sqrt(2.0)
        inner = max(0.0, 1.0 - softness)
        t = np.clip((d - inner) / max(1e-3, 1.0 - inner), 0.0, 1.0)
        mask = 1.0 - amount * (t * t * (3.0 - 2.0 * t))  # smoothstep
        out = image.astype(np.float32) * mask[..., None]
        return np.clip(out, 0, 255).astype(np.uint8)
