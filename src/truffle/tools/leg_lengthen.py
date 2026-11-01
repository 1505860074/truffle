"""长腿：基于人体姿态纵向拉长胯部以下的腿部区域，仅作用于人物，背景不变。"""

from __future__ import annotations

import cv2
import numpy as np

from ..cv.analyzer import POSE_L_HIP, POSE_R_HIP, refine_mask
from .base import BaseTool, ToolContext, ToolParameter


class LegLengthenTool(BaseTool):
    name = "leg_lengthen"
    description = "长腿：拉长腿部比例，仅作用于人物区域，背景保持不变。需要能识别到人体。"
    parameters = [
        ToolParameter("strength", "拉长强度，建议 0.2~0.5。", "number", 0.0, 1.0, 0.3),
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.3) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        pose = ctx.pose(image)
        if pose is None:
            return image.copy()
        hip_y = float((pose[POSE_L_HIP][1] + pose[POSE_R_HIP][1]) / 2.0)
        h, w = image.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        factor = 1.0 + strength * 0.4
        map_y = np.where(yy > hip_y, hip_y + (yy - hip_y) / factor, yy).astype(np.float32)
        stretched = cv2.remap(
            image, xx, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
        )

        fg = ctx.foreground(image)
        if fg is None:
            return stretched
        fg = refine_mask(image, fg, radius=10)
        alpha = (fg.astype(np.float32) / 255.0)[..., None]
        out = stretched.astype(np.float32) * alpha + image.astype(np.float32) * (1 - alpha)
        return np.clip(out, 0, 255).astype(np.uint8)
