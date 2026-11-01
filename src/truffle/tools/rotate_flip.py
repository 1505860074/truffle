"""旋转 / 翻转：90° 旋转与水平/垂直镜像。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class RotateFlipTool(BaseTool):
    name = "rotate_flip"
    description = "旋转或翻转图片：顺时针 90° 的倍数旋转，或水平/垂直镜像。"
    parameters = [
        ToolParameter("rotate", "顺时针旋转角度。", "integer", 0, 270, 0, enum=[0, 90, 180, 270]),
        ToolParameter(
            "flip", "翻转方向。", "string", default="none",
            enum=["none", "horizontal", "vertical"],
        ),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        rotate: int = 0, flip: str = "none",
    ) -> np.ndarray:
        out = image
        if rotate in (90, 180, 270):
            k = {90: 3, 180: 2, 270: 1}[int(rotate)]  # np.rot90 为逆时针，故取反
            out = np.ascontiguousarray(np.rot90(out, k))
        if flip == "horizontal":
            out = cv2.flip(out, 1)
        elif flip == "vertical":
            out = cv2.flip(out, 0)
        return np.ascontiguousarray(out.copy())
