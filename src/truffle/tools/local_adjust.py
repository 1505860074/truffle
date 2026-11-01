"""局部调整：矩形/椭圆/径向/线性蒙版内曝光、亮度、对比、饱和度。"""

from __future__ import annotations

import cv2
import numpy as np

from ..core.masks import apply_mask, mask_from_params
from .base import BaseTool, ToolContext, ToolParameter


class LocalAdjustTool(BaseTool):
    name = "local_adjust"
    description = "在指定局部区域内调整曝光/亮度/对比度/饱和度；区域形状支持矩形、椭圆、径向、线性渐变。"
    parameters = [
        ToolParameter("shape", "蒙版形状。", "string", enum=["rect", "ellipse", "radial", "linear"], default="radial"),
        ToolParameter("x1", "区域左上/中心/渐变起点的 X（0~1）。", "number", 0.0, 1.0, 0.2),
        ToolParameter("y1", "区域左上/中心/渐变起点的 Y（0~1）。", "number", 0.0, 1.0, 0.2),
        ToolParameter("x2", "区域右下/半径终点/渐变终点的 X（0~1）。", "number", 0.0, 1.0, 0.8),
        ToolParameter("y2", "区域右下/半径终点/渐变终点的 Y（0~1）。", "number", 0.0, 1.0, 0.8),
        ToolParameter("feather", "羽化，0~0.5。", "number", 0.0, 0.5, 0.2),
        ToolParameter("exposure", "局部曝光 EV，-2~2。", "number", -2.0, 2.0, 0.0),
        ToolParameter("brightness", "局部亮度，-1~1。", "number", -1.0, 1.0, 0.0),
        ToolParameter("contrast", "局部对比，-1~1。", "number", -1.0, 1.0, 0.0),
        ToolParameter("saturation", "局部饱和，-1~1。", "number", -1.0, 1.0, 0.0),
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
        feather: float = 0.2,
        exposure: float = 0.0,
        brightness: float = 0.0,
        contrast: float = 0.0,
        saturation: float = 0.0,
        invert: bool = False,
    ) -> np.ndarray:
        if not any((abs(exposure) > 1e-3, abs(brightness) > 1e-3,
                    abs(contrast) > 1e-3, abs(saturation) > 1e-3)):
            return image.copy()
        out = image.astype(np.float32)
        if abs(exposure) > 1e-3:
            out = np.power(np.clip(out / 255.0, 0.0, 1.0), 1.0 / (2.0 ** exposure)) * 255.0
        out += brightness * 60.0
        if abs(contrast) > 1e-3:
            out = (out - 127.5) * (1.0 + contrast) + 127.5
        out = np.clip(out, 0, 255).astype(np.uint8)
        if abs(saturation) > 1e-3:
            hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + saturation), 0, 255)
            out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        mask = mask_from_params(image.shape[0], image.shape[1], {
            "shape": shape, "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "feather": feather, "invert": invert,
        })
        return apply_mask(image, out, mask)
