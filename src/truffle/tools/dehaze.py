"""去雾：暗通道先验的简化实现，提升通透感。"""

from __future__ import annotations

import cv2
import numpy as np

from .base import BaseTool, ToolContext, ToolParameter


class DehazeTool(BaseTool):
    name = "dehaze"
    description = "去雾：减轻灰蒙蒙的雾感，提升通透度。"
    parameters = [
        ToolParameter("strength", "去雾强度，0 无效果。", "number", 0.0, 1.0, 0.5),
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.5) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        img = image.astype(np.float32) / 255.0
        dark = np.min(img, axis=2)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        dark = cv2.erode(dark, kernel)

        flat = np.sort(dark.ravel())[::-1]
        num = max(1, int(0.001 * flat.size))
        threshold = flat[num - 1]
        mask = dark >= threshold
        A = img[mask].mean(axis=0) if mask.any() else np.array([1.0, 1.0, 1.0], np.float32)
        A = np.clip(A, 0.3, 1.0)

        t = 1.0 - strength * dark / float(A.mean())
        t = np.clip(t, 0.15, 1.0)
        out = np.empty_like(img)
        for c in range(3):
            out[..., c] = (img[..., c] - A[c]) / t + A[c]
        return (np.clip(out, 0, 1) * 255).astype(np.uint8)
