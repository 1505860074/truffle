"""大眼：以眼睛中心为原点向外扩张眼部区域。"""

from __future__ import annotations

import numpy as np

from ..cv.analyzer import EYE_LEFT, EYE_RIGHT
from ..cv.warp import warp_by_points
from .base import BaseTool, ToolContext, ToolParameter


class EnlargeEyesTool(BaseTool):
    name = "enlarge_eyes"
    description = "放大眼睛：让眼睛更明亮有神。会先检测眼睛关键点再作用。"
    parameters = [
        ToolParameter(
            "strength",
            "大眼强度，0 无效果，1 最强。建议 0.2~0.5。",
            "number",
            minimum=0.0,
            maximum=1.0,
            default=0.3,
        )
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.3) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        out = image
        for face in analysis.faces:
            if face.landmarks is None:
                continue
            lm = face.landmarks
            for eye_idx in (EYE_LEFT, EYE_RIGHT):
                pts = lm[eye_idx]
                center = pts.mean(axis=0)
                radius = max(float(np.ptp(pts[:, 0])), float(np.ptp(pts[:, 1]))) * 1.8
                scale = 0.18 * strength
                src = [(float(x), float(y)) for x, y in pts]
                disp = [
                    (float((x - center[0]) * scale), float((y - center[1]) * scale))
                    for x, y in pts
                ]
                out = warp_by_points(out, src, disp, max(radius, 18.0))
        return out
