"""虹膜增强：提亮虹膜、增加虹膜饱和度与清晰度。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import EYE_LEFT, EYE_RIGHT
from ..core.masks import apply_mask
from .base import BaseTool, ToolContext, ToolParameter


class IrisTool(BaseTool):
    name = "iris"
    description = "虹膜增强：让眼睛更亮、虹膜颜色更清晰。需要人脸关键点。"
    parameters = [
        ToolParameter("strength", "整体强度，0~1。", "number", 0.0, 1.0, 0.35),
        ToolParameter("saturation", "虹膜饱和度，0~1。", "number", 0.0, 1.0, 0.25),
        ToolParameter("brightness", "虹膜提亮，0~1。", "number", 0.0, 1.0, 0.15),
        ToolParameter("sharpen", "虹膜锐化，0~1。", "number", 0.0, 1.0, 0.2),
    ]

    def apply(
        self,
        image: np.ndarray,
        ctx: ToolContext,
        strength: float = 0.35,
        saturation: float = 0.25,
        brightness: float = 0.15,
        sharpen: float = 0.2,
    ) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for face in analysis.faces:
            if face.landmarks is None:
                continue
            lm = face.landmarks
            for indices in (EYE_LEFT, EYE_RIGHT):
                pts = lm[indices]
                cx, cy = float(pts[:, 0].mean()), float(pts[:, 1].mean())
                ew = float(np.ptp(pts[:, 0]))
                eh = float(np.ptp(pts[:, 1]))
                rx = max(2, int(ew * 0.34))
                ry = max(2, int(eh * 0.42))
                cv2.ellipse(mask, (int(cx), int(cy)), (rx, ry), 0, 0, 360, 255, -1)
        if not mask.any():
            return image.copy()
        mask = cv2.GaussianBlur(mask, (0, 0), 2)

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + saturation * strength), 0, 255)
        hsv[..., 2] = np.clip(hsv[..., 2] + brightness * strength * 40.0, 0, 255)
        adjusted = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
        if sharpen > 0:
            blur = cv2.GaussianBlur(adjusted, (0, 0), 1.2)
            adjusted = cv2.addWeighted(adjusted, 1.0 + sharpen * strength, blur, -sharpen * strength, 0)
        return apply_mask(image, adjusted, mask)
