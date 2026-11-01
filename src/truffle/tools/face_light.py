"""面部光影：在额头与脸颊区域做柔和的提亮/加深。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import EYE_LEFT, EYE_RIGHT, MOUTH_OUTER
from ..core.masks import apply_mask
from .base import BaseTool, ToolContext, ToolParameter


class FaceLightTool(BaseTool):
    name = "face_light"
    description = "面部光影：提亮额头/苹果肌或压暗轮廓，让脸更立体。需要人脸关键点。"
    parameters = [
        ToolParameter("strength", "光影强度，-1 压暗轮廓，1 提亮面部。", "number", -1.0, 1.0, 0.25),
        ToolParameter("warmth", "暖色偏移，-1 冷、1 暖。", "number", -1.0, 1.0, 0.05),
        ToolParameter("feather", "羽化，0~1。", "number", 0.0, 1.0, 0.45),
    ]

    def apply(
        self,
        image: np.ndarray,
        ctx: ToolContext,
        strength: float = 0.25,
        warmth: float = 0.05,
        feather: float = 0.45,
    ) -> np.ndarray:
        if abs(strength) < 0.01 and abs(warmth) < 0.01:
            return image.copy()
        analysis = ctx.analyze(image)
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for face in analysis.faces:
            if face.landmarks is None:
                continue
            lm = face.landmarks
            x, y, bw, bh = face.box
            # 额头
            cv2.ellipse(
                mask, (int(face.center[0]), int(y + bh * 0.22)),
                (int(bw * 0.32), int(bh * 0.18)), 0, 0, 360, 170, -1,
            )
            # 苹果肌
            for cx in (face.center[0] - bw * 0.22, face.center[0] + bw * 0.22):
                cv2.ellipse(
                    mask, (int(cx), int(y + bh * 0.62)),
                    (int(bw * 0.2), int(bh * 0.16)), 0, 0, 360, 150, -1,
                )
            # 五官保护
            protect = np.zeros((h, w), dtype=np.uint8)
            for indices in (EYE_LEFT, EYE_RIGHT, MOUTH_OUTER):
                pts = np.array([lm[i] for i in indices], dtype=np.int32)
                cv2.fillConvexPoly(protect, cv2.convexHull(pts), 255)
            mask[protect > 0] = 0
        if not mask.any():
            return image.copy()
        if feather > 0:
            mask = cv2.GaussianBlur(mask, (0, 0), max(1.0, feather * min(h, w) * 0.02))

        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
        l, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
        if strength > 0:
            l += (255.0 - l) * (0.22 * strength)
        else:
            l *= 1.0 + 0.22 * strength
        a += warmth * 8.0
        b += warmth * 10.0
        adjusted = cv2.cvtColor(
            np.clip(cv2.merge([l, a, b]), 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR
        )
        return apply_mask(image, adjusted, mask)
