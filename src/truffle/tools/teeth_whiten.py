"""牙齿美白：在内唇区域内提亮牙齿、减轻黄气。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import MOUTH_INNER
from .base import BaseTool, ToolContext, ToolParameter


class TeethWhitenTool(BaseTool):
    name = "teeth_whiten"
    description = "牙齿美白：自动定位嘴部，提亮牙齿、减轻黄气。需要能识别到人脸。"
    parameters = [
        ToolParameter("strength", "美白强度，0 无效果。", "number", 0.0, 1.0, 0.5),
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.5) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for face in analysis.faces:
            if face.landmarks is None:
                continue
            pts = face.landmarks[MOUTH_INNER].astype(np.int32)
            cv2.fillConvexPoly(mask, cv2.convexHull(pts), 255)
        if not mask.any():
            return image.copy()
        mask = cv2.GaussianBlur(mask, (0, 0), 3)

        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
        L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
        L += (255.0 - L) * (0.35 * strength)
        b += (128.0 - b) * (0.25 * strength)
        whitened = cv2.cvtColor(
            np.clip(cv2.merge([L, a, b]), 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR
        )
        alpha = (mask.astype(np.float32) / 255.0)[..., None]
        out = image.astype(np.float32) * (1 - alpha) + whitened.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
