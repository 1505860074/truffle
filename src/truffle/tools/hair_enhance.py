"""头发增强：用头发蒙版提升光泽、对比与顺滑度。"""

from __future__ import annotations

import cv2
import numpy as np

from ..core.masks import apply_mask
from ..cv.parsing import FaceParser
from .base import BaseTool, ToolContext, ToolParameter


class HairEnhanceTool(BaseTool):
    name = "hair_enhance"
    description = "头发增强：提升发丝光泽与对比、轻微顺滑。优先使用本地人脸解析模型，缺失时用启发式头发蒙版。"
    parameters = [
        ToolParameter("strength", "整体强度，0~1。", "number", 0.0, 1.0, 0.3),
        ToolParameter("shine", "光泽/高光，0~1。", "number", 0.0, 1.0, 0.2),
        ToolParameter("smooth", "顺滑/降噪，0~1。", "number", 0.0, 1.0, 0.15),
    ]

    def __init__(self) -> None:
        self._parser = FaceParser()

    def apply(
        self,
        image: np.ndarray,
        ctx: ToolContext,
        strength: float = 0.3,
        shine: float = 0.2,
        smooth: float = 0.15,
    ) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        try:
            mask = self._parser.hair_mask(image, analysis)
        except Exception:
            return image.copy()
        if mask is None or not np.any(mask > 32):
            return image.copy()
        out = image.astype(np.float32)
        if shine > 0:
            blur = cv2.GaussianBlur(image, (0, 0), 6.0).astype(np.float32)
            out = cv2.addWeighted(out, 1.0 + shine * strength, blur, -shine * strength, 0)
        if smooth > 0:
            smoothed = cv2.bilateralFilter(image, 7, 30.0, 30.0)
            out = out * (1 - smooth * strength) + smoothed.astype(np.float32) * (smooth * strength)
        out = np.clip(out, 0, 255).astype(np.uint8)
        return apply_mask(image, out, mask)
