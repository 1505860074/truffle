"""高光 / 阴影：压暗高光、提亮暗部，找回亮暗细节。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class ToneRecoveryTool(BaseTool):
    name = "tone_recovery"
    description = "高光/阴影恢复：压暗过亮的高光、提亮过暗的阴影，找回细节。"
    parameters = [
        ToolParameter("highlights", "高光，负数压暗高光、正数提亮高光。", "number", -1.0, 1.0, 0.0),
        ToolParameter("shadows", "阴影，正数提亮暗部、负数压暗暗部。", "number", -1.0, 1.0, 0.0),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        highlights: float = 0.0, shadows: float = 0.0,
    ) -> np.ndarray:
        if highlights == 0 and shadows == 0:
            return image.copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
        hi = np.clip((gray - 128.0) / 127.0, 0.0, 1.0)
        lo = np.clip((128.0 - gray) / 128.0, 0.0, 1.0)
        delta = (highlights * hi + shadows * lo) * 80.0
        out = image.astype(np.float32) + delta[..., None]
        return np.clip(out, 0, 255).astype(np.uint8)
