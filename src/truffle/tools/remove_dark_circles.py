"""去黑眼圈：在眼下区域提亮、减淡暗沉。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import EYE_LEFT, EYE_RIGHT
from .base import BaseTool, ToolContext, ToolParameter


class RemoveDarkCirclesTool(BaseTool):
    name = "remove_dark_circles"
    description = "去黑眼圈：提亮眼下的暗沉区域。需要能识别到人脸。"
    parameters = [
        ToolParameter("strength", "作用强度，0 无效果。", "number", 0.0, 1.0, 0.5),
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
            lm = face.landmarks
            for eye_idx in (EYE_LEFT, EYE_RIGHT):
                pts = lm[eye_idx]
                cx = float(pts[:, 0].mean())
                cy = float(pts[:, 1].mean())
                ew = float(np.ptp(pts[:, 0]))
                eh = float(np.ptp(pts[:, 1]))
                ucy = cy + eh * 1.3
                cv2.ellipse(
                    mask, (int(cx), int(ucy)),
                    (max(3, int(ew * 0.75)), max(2, int(eh * 0.85))),
                    0, 0, 360, 255, -1,
                )
        if not mask.any():
            return image.copy()
        mask = cv2.GaussianBlur(mask, (0, 0), 5)

        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
        L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
        L += (255.0 - L) * (0.30 * strength)
        a += (128.0 - a) * (0.15 * strength)
        brightened = cv2.cvtColor(
            np.clip(cv2.merge([L, a, b]), 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR
        )
        alpha = (mask.astype(np.float32) / 255.0)[..., None]
        out = image.astype(np.float32) * (1 - alpha) + brightened.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
