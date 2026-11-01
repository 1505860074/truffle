"""瘦身 / 瘦腰：基于人体姿态横向收窄躯干，并限制在人物区域内（少拖背景）。"""

from __future__ import annotations

import numpy as np

from ..cv.analyzer import (
    POSE_L_HIP,
    POSE_L_SHOULDER,
    POSE_R_HIP,
    POSE_R_SHOULDER,
    refine_mask,
)
from ..cv.warp import warp_by_points
from .base import BaseTool, ToolContext, ToolParameter


class BodySlimTool(BaseTool):
    name = "body_slim"
    description = "瘦身/瘦腰：让腰身更纤细，仅作用于人物区域，减少背景变形。需要能识别到人体。"
    parameters = [
        ToolParameter("strength", "收窄强度，建议 0.3~0.6，过高会不自然。", "number", 0.0, 1.0, 0.4),
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.4) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        pose = ctx.pose(image)
        if pose is None:
            return image.copy()
        lsh, rsh = pose[POSE_L_SHOULDER], pose[POSE_R_SHOULDER]
        lhip, rhip = pose[POSE_L_HIP], pose[POSE_R_HIP]
        cx = float((lsh[0] + rsh[0] + lhip[0] + rhip[0]) / 4.0)

        # 肩、腰、胯三处 + 两侧中点，控制更均匀
        src: list[tuple[float, float]] = []
        disp: list[tuple[float, float]] = []
        pairs = [(lsh, rsh), ((lsh + lhip) / 2, (rsh + rhip) / 2), (lhip, rhip)]
        for left, right in pairs:
            for x, y in (left, right, ((left + right) / 2)):
                x, y = float(x), float(y)
                src.append((x, y))
                disp.append(((cx - x) * 0.15 * strength, 0.0))

        width = max(abs(lsh[0] - rsh[0]), abs(lhip[0] - rhip[0]))
        radius = max(width * 1.15, 30.0)
        warped = warp_by_points(image, src, disp, radius, falloff="gauss")

        # 限制在人物掩膜内，避免背景被拖动
        fg = ctx.foreground(image)
        if fg is None:
            return warped
        fg = refine_mask(image, fg, radius=10)
        alpha = (fg.astype(np.float32) / 255.0)[..., None]
        out = warped.astype(np.float32) * alpha + image.astype(np.float32) * (1 - alpha)
        return np.clip(out, 0, 255).astype(np.uint8)
