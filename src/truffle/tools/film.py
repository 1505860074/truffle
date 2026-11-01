"""胶片感：颗粒（噪点）与褪色。"""

from __future__ import annotations

import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class FilmTool(BaseTool):
    name = "film"
    description = "胶片质感：叠加颗粒噪点并做褪色处理。"
    parameters = [
        ToolParameter("grain", "颗粒（噪点）强度，0 无效果。", "number", 0.0, 1.0, 0.3),
        ToolParameter("fade", "褪色程度，越大越发灰、对比越低。", "number", 0.0, 1.0, 0.2),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        grain: float = 0.3, fade: float = 0.2,
    ) -> np.ndarray:
        if grain == 0 and fade == 0:
            return image.copy()
        out = image.astype(np.float32)
        if fade:
            out = out * (1.0 - fade * 0.35) + 45.0 * fade
        if grain:
            rng = np.random.default_rng(0)
            noise = rng.normal(0.0, 1.0, out.shape[:2]).astype(np.float32)
            out += noise[..., None] * grain * 38.0
        return np.clip(out, 0, 255).astype(np.uint8)
