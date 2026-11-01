"""克隆图章：把源区域复制到目标区域，带柔边与透明度。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class CloneTool(BaseTool):
    name = "clone"
    description = "克隆图章：从源点复制一块圆形区域到目标点，用于去杂物、补背景。坐标均为 0~1。"
    parameters = [
        ToolParameter("src_x", "源点 X（0~1）。", "number", 0.0, 1.0, 0.3),
        ToolParameter("src_y", "源点 Y（0~1）。", "number", 0.0, 1.0, 0.3),
        ToolParameter("dst_x", "目标点 X（0~1）。", "number", 0.0, 1.0, 0.7),
        ToolParameter("dst_y", "目标点 Y（0~1）。", "number", 0.0, 1.0, 0.7),
        ToolParameter("radius", "半径占图像短边的比例，0.01~0.4。", "number", 0.01, 0.4, 0.08),
        ToolParameter("feather", "羽化，0~0.8。", "number", 0.0, 0.8, 0.25),
        ToolParameter("opacity", "不透明度，0~1。", "number", 0.0, 1.0, 1.0),
    ]

    def apply(
        self,
        image: np.ndarray,
        ctx: ToolContext,
        src_x: float = 0.3,
        src_y: float = 0.3,
        dst_x: float = 0.7,
        dst_y: float = 0.7,
        radius: float = 0.08,
        feather: float = 0.25,
        opacity: float = 1.0,
    ) -> np.ndarray:
        if opacity <= 0:
            return image.copy()
        h, w = image.shape[:2]
        r = max(2, int(radius * min(h, w)))
        sx, sy = int(src_x * w), int(src_y * h)
        dx, dy = int(dst_x * w), int(dst_y * h)
        x0, x1 = max(0, dx - r), min(w, dx + r)
        y0, y1 = max(0, dy - r), min(h, dy + r)
        if x1 <= x0 or y1 <= y0:
            return image.copy()
        src_x0 = max(0, min(w - (x1 - x0), sx - r))
        src_y0 = max(0, min(h - (y1 - y0), sy - r))
        patch = image[src_y0:src_y0 + (y1 - y0), src_x0:src_x0 + (x1 - x0)]
        mask = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
        cv2.circle(mask, (dx - x0, dy - y0), r, 255, -1)
        if feather > 0:
            mask = cv2.GaussianBlur(mask, (0, 0), max(0.5, feather * r))
        alpha = (mask.astype(np.float32) / 255.0 * opacity)[..., None]
        region = image[y0:y1, x0:x1].astype(np.float32)
        blended = region * (1 - alpha) + patch.astype(np.float32) * alpha
        out = image.copy()
        out[y0:y1, x0:x1] = np.clip(blended, 0, 255).astype(np.uint8)
        return out
