"""曲线：参数化影调曲线（黑场 / 阴影 / 中间调 / 高光 / 白场），作用于亮度。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class CurvesTool(BaseTool):
    name = "curves"
    description = "曲线：按影调分区调整明暗，找回或压制层次。"
    parameters = [
        ToolParameter("black", "黑场，正数提亮暗部、负数压黑。", "number", -1.0, 1.0, 0.0),
        ToolParameter("shadows", "阴影。", "number", -1.0, 1.0, 0.0),
        ToolParameter("midtones", "中间调。", "number", -1.0, 1.0, 0.0),
        ToolParameter("highlights", "高光。", "number", -1.0, 1.0, 0.0),
        ToolParameter("white", "白场，正数提亮亮部、负数压白。", "number", -1.0, 1.0, 0.0),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        black: float = 0.0, shadows: float = 0.0, midtones: float = 0.0,
        highlights: float = 0.0, white: float = 0.0,
    ) -> np.ndarray:
        if black == 0 and shadows == 0 and midtones == 0 and highlights == 0 and white == 0:
            return image.copy()
        x = np.linspace(0.0, 1.0, 256, dtype=np.float32)
        y = x.copy()
        y = y + black * (1.0 - y)
        y = y + white * y
        y += shadows * np.exp(-((x - 0.25) ** 2) / (2 * 0.15 ** 2))
        y += midtones * np.exp(-((x - 0.50) ** 2) / (2 * 0.20 ** 2))
        y += highlights * np.exp(-((x - 0.75) ** 2) / (2 * 0.15 ** 2))
        table = np.clip(y, 0.0, 1.0) * 255.0
        table = np.clip(table, 0, 255).astype(np.uint8)

        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        lab[..., 0] = cv2.LUT(lab[..., 0], table)
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
