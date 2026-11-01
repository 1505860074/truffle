"""发色：给头发区域上色（估计为脸部上方、非皮肤、偏暗的区域）。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import FACE_OVAL
from .base import BaseTool, ToolContext, ToolParameter


class HairColorTool(BaseTool):
    name = "hair_color"
    description = "发色：给头发换色/上色（估计头发区域，效果因发型而异）。需要能识别到人脸。"
    parameters = [
        ToolParameter("hue", "目标色相，0~1（0=红，0.1=橙黄，0.33=绿，0.6=蓝，0.8=紫）。", "number", 0.0, 1.0, 0.05),
        ToolParameter("strength", "上色强度，0 无效果。", "number", 0.0, 1.0, 0.5),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        hue: float = 0.05, strength: float = 0.5,
    ) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for face in analysis.faces:
            if face.landmarks is None:
                continue
            oval = face.landmarks[FACE_OVAL]
            xs, ys = oval[:, 0], oval[:, 1]
            x0, x1 = float(xs.min()), float(xs.max())
            y0, y1 = float(ys.min()), float(ys.max())
            fw, fh = x1 - x0, y1 - y0
            top = max(0, int(y0 - fh * 0.9))
            bot = int(y0 + fh * 0.15)
            left = max(0, int(x0 - fw * 0.15))
            right = min(w, int(x1 + fw * 0.15))
            mask[top:bot, left:right] = 255
        if not mask.any():
            return image.copy()

        skin = analysis.skin_mask
        if skin is not None:
            mask[skin > 128] = 0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mask = cv2.bitwise_and(mask, (gray < 170).astype(np.uint8) * 255)
        mask = cv2.GaussianBlur(mask, (0, 0), 3)
        alpha = (mask.astype(np.float32) / 255.0 * strength)[..., None]

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 0] = hue * 180.0
        hsv[..., 1] = np.clip(hsv[..., 1] * 1.15 + 30.0, 0, 255)
        tinted = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        out = image.astype(np.float32) * (1 - alpha) + tinted.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
