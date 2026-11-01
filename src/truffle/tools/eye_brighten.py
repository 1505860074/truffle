"""眼睛提亮：提亮眼睛、让眼神更有神，眼白更干净。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import EYE_LEFT, EYE_RIGHT
from .base import BaseTool, ToolContext, ToolParameter


class EyeBrightenTool(BaseTool):
    name = "eye_brighten"
    description = "眼睛提亮：让眼睛更亮更有神，眼白更干净。需要能识别到人脸。"
    parameters = [
        ToolParameter("strength", "提亮强度，0 无效果。", "number", 0.0, 1.0, 0.5),
        ToolParameter("sclera", "眼白去黄强度。", "number", 0.0, 1.0, 0.3),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        strength: float = 0.5, sclera: float = 0.3,
    ) -> np.ndarray:
        if strength <= 0 and sclera <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for face in analysis.faces:
            if face.landmarks is None:
                continue
            for idx in (EYE_LEFT, EYE_RIGHT):
                pts = face.landmarks[idx].astype(np.int32)
                cv2.fillConvexPoly(mask, cv2.convexHull(pts), 255)
        if not mask.any():
            return image.copy()
        mask = cv2.GaussianBlur(mask, (0, 0), 4)

        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
        L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
        L += (255.0 - L) * (0.35 * strength)
        b += (128.0 - b) * (0.30 * sclera)
        bright = cv2.cvtColor(
            np.clip(cv2.merge([L, a, b]), 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR
        )
        alpha = (mask.astype(np.float32) / 255.0)[..., None]
        out = image.astype(np.float32) * (1 - alpha) + bright.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
