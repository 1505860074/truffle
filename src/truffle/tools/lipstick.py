"""口红：给嘴唇区域上色（外唇轮廓内、内唇外）。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import MOUTH_INNER, MOUTH_OUTER
from .base import BaseTool, ToolContext, ToolParameter


class LipstickTool(BaseTool):
    name = "lipstick"
    description = "口红：给嘴唇上色。需要能识别到人脸。"
    parameters = [
        ToolParameter("hue", "口红色相，0~1（约 0.95~1.0 为红）。", "number", 0.0, 1.0, 0.98),
        ToolParameter("strength", "上色强度，0 无效果。", "number", 0.0, 1.0, 0.5),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        hue: float = 0.98, strength: float = 0.5,
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
            outer = cv2.convexHull(lm[MOUTH_OUTER].astype(np.int32))
            inner = cv2.convexHull(lm[MOUTH_INNER].astype(np.int32))
            cv2.fillPoly(mask, [outer], 255)
            cv2.fillPoly(mask, [inner], 0)
        if not mask.any():
            return image.copy()
        mask = cv2.GaussianBlur(mask, (0, 0), 3)
        alpha = (mask.astype(np.float32) / 255.0 * strength)[..., None]

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 0] = hue * 180.0
        hsv[..., 1] = np.clip(hsv[..., 1] * 1.2 + 40.0, 0, 255)
        hsv[..., 2] = np.clip(hsv[..., 2] * 0.95, 0, 255)
        tinted = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        out = image.astype(np.float32) * (1 - alpha) + tinted.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
