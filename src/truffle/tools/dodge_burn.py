"""减淡 / 加深：在局部蒙版内提亮或压暗，模拟 dodge & burn。"""

from __future__ import annotations

import cv2
import numpy as np

from ..core.masks import apply_mask, mask_from_params
from .base import BaseTool, ToolContext, ToolParameter


class DodgeBurnTool(BaseTool):
    name = "dodge_burn"
    description = "局部减淡/加深：在矩形、椭圆、径向或线性区域内提亮或压暗，适合塑造光影。"
    parameters = [
        ToolParameter("shape", "蒙版形状。", "string", enum=["rect", "ellipse", "radial", "linear"], default="radial"),
        ToolParameter("x1", "区域 X1（0~1）。", "number", 0.0, 1.0, 0.2),
        ToolParameter("y1", "区域 Y1（0~1）。", "number", 0.0, 1.0, 0.2),
        ToolParameter("x2", "区域 X2（0~1）。", "number", 0.0, 1.0, 0.8),
        ToolParameter("y2", "区域 Y2（0~1）。", "number", 0.0, 1.0, 0.8),
        ToolParameter("feather", "羽化，0~0.5。", "number", 0.0, 0.5, 0.25),
        ToolParameter("amount", "正数提亮（减淡），负数压暗（加深），-1~1。", "number", -1.0, 1.0, 0.25),
        ToolParameter("invert", "反转蒙版。", "boolean", default=False),
    ]

    def apply(
        self,
        image: np.ndarray,
        ctx: ToolContext,
        shape: str = "radial",
        x1: float = 0.2,
        y1: float = 0.2,
        x2: float = 0.8,
        y2: float = 0.8,
        feather: float = 0.25,
        amount: float = 0.25,
        invert: bool = False,
    ) -> np.ndarray:
        if abs(amount) < 0.01:
            return image.copy()
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
        l = lab[..., 0] / 255.0
        if amount > 0:
            l = 1.0 - (1.0 - l) * (1.0 - 0.55 * amount)
        else:
            l = l * (1.0 + 0.55 * amount)
        lab[..., 0] = np.clip(l, 0.0, 1.0) * 255.0
        adjusted = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
        mask = mask_from_params(image.shape[0], image.shape[1], {
            "shape": shape, "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "feather": feather, "invert": invert,
        })
        return apply_mask(image, adjusted, mask)
