"""色温 / 色调：冷暖偏移与绿品校正。"""

from __future__ import annotations

import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class ColorTempTool(BaseTool):
    name = "color_temp"
    description = "调整色温与色调：色温控制冷暖，色调控制偏绿/偏品红。"
    parameters = [
        ToolParameter("temperature", "色温，负数偏冷(蓝)、正数偏暖(橙)。", "number", -1.0, 1.0, 0.0),
        ToolParameter("tint", "色调，负数偏绿、正数偏品红。", "number", -1.0, 1.0, 0.0),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        temperature: float = 0.0, tint: float = 0.0,
    ) -> np.ndarray:
        if temperature == 0 and tint == 0:
            return image.copy()
        out = image.astype(np.float32)
        out[..., 2] += temperature * 40.0   # R
        out[..., 0] -= temperature * 40.0   # B
        out[..., 2] += tint * 25.0          # R
        out[..., 0] += tint * 25.0          # B
        out[..., 1] -= tint * 25.0          # G
        return np.clip(out, 0, 255).astype(np.uint8)
