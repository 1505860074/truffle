"""曝光：按 EV 做线性提亮/压暗，保护高光。"""

from __future__ import annotations

import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class ExposureTool(BaseTool):
    name = "exposure"
    description = "曝光补偿：以 EV 为单位提亮或压暗画面，保留高光层次。"
    parameters = [
        ToolParameter("ev", "曝光补偿，-2 压暗两档，+2 提亮两档。", "number", -2.0, 2.0, 0.0),
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, ev: float = 0.0) -> np.ndarray:
        if abs(ev) < 0.01:
            return image.copy()
        out = image.astype(np.float32) / 255.0
        lifted = np.power(np.clip(out, 0.0, 1.0), 1.0 / (2.0 ** ev))
        return np.clip(lifted * 255.0, 0, 255).astype(np.uint8)
