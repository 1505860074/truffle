"""色阶：黑场、白场与中间调 gamma。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class LevelsTool(BaseTool):
    name = "levels"
    description = "色阶：设置黑场、白场和中间调 gamma，找回影调层次。"
    parameters = [
        ToolParameter("black", "黑场，0~0.4，越大暗部越黑。", "number", 0.0, 0.4, 0.0),
        ToolParameter("white", "白场，0~0.4，越大高光越白。", "number", 0.0, 0.4, 0.0),
        ToolParameter("gamma", "中间调 gamma，0.5~1.8，越大中间调越亮。", "number", 0.5, 1.8, 1.0),
    ]

    def apply(
        self,
        image: np.ndarray,
        ctx: ToolContext,
        black: float = 0.0,
        white: float = 0.0,
        gamma: float = 1.0,
    ) -> np.ndarray:
        if black == 0 and white == 0 and abs(gamma - 1.0) < 0.01:
            return image.copy()
        x = np.linspace(0.0, 1.0, 256, dtype=np.float32)
        lo = float(np.clip(black, 0.0, 0.45))
        hi = float(np.clip(1.0 - white, 0.55, 1.0))
        y = np.clip((x - lo) / max(1e-6, hi - lo), 0.0, 1.0)
        y = np.power(y, 1.0 / max(0.1, gamma))
        table = np.clip(y * 255.0, 0, 255).astype(np.uint8)
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        lab[..., 0] = cv2.LUT(lab[..., 0], table)
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
