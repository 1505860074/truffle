"""祛痘祛斑：在皮肤区域内检测细小暗斑并 inpaint 修补，保护五官/眉毛/嘴/鼻。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import (
    EYEBROW_LEFT,
    EYEBROW_RIGHT,
    EYE_LEFT,
    EYE_RIGHT,
    MOUTH_OUTER,
    NOSE,
    refine_mask,
)
from .base import BaseTool, ToolContext, ToolParameter

_PROTECT = EYE_LEFT + EYE_RIGHT + EYEBROW_LEFT + EYEBROW_RIGHT + MOUTH_OUTER + NOSE


class RemoveBlemishTool(BaseTool):
    name = "remove_blemish"
    description = "祛痘祛斑：自动识别并淡化皮肤上的痘痘、色斑等细小瑕疵，保护五官与眉毛。"
    parameters = [
        ToolParameter("strength", "作用强度，0 无效果，1 最强。建议 0.4~0.7。", "number", 0.0, 1.0, 0.6),
        ToolParameter("threshold", "斑点判定阈值（灰度差），越小识别越多、越激进。建议 8~20。", "number", 4.0, 40.0, 12.0),
    ]

    def apply(
        self, image: np.ndarray, ctx: ToolContext,
        strength: float = 0.6, threshold: float = 12.0,
    ) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        skin = analysis.skin_mask
        if skin is None:
            return image.copy()
        skin = refine_mask(image, skin, radius=6)

        h, w = image.shape[:2]
        # 五官保护掩膜：眼/眉/嘴/鼻附近不当作斑点
        protect = np.zeros((h, w), dtype=np.uint8)
        radius = max(4, int(0.012 * max(h, w)))
        for face in analysis.faces:
            if face.landmarks is None:
                continue
            for idx in _PROTECT:
                x, y = face.landmarks[idx]
                cv2.circle(protect, (int(x), int(y)), radius, 255, -1)
        if protect.any():
            protect = cv2.dilate(protect, np.ones((5, 5), np.uint8), iterations=1)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        background = cv2.medianBlur(gray, 21)
        diff = background.astype(np.int16) - gray.astype(np.int16)
        candidate = ((diff > threshold) & (skin > 128) & (protect == 0)).astype(np.uint8) * 255

        num, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
        keep = np.zeros((h, w), dtype=np.uint8)
        max_area = 0.0008 * h * w
        for i in range(1, num):
            area = stats[i, cv2.CC_STAT_AREA]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            if 2 <= area <= max_area and bw <= 0.05 * w and bh <= 0.05 * h:
                keep[labels == i] = 255

        if not keep.any():
            return image.copy()

        keep = cv2.dilate(keep, np.ones((3, 3), np.uint8), iterations=1)
        healed = cv2.inpaint(image, keep, 3, cv2.INPAINT_TELEA)
        alpha = (keep.astype(np.float32) / 255.0 * strength)[..., None]
        out = image.astype(np.float32) * (1 - alpha) + healed.astype(np.float32) * alpha
        return np.clip(out, 0, 255).astype(np.uint8)
