"""瘦脸：沿下颌/脸颊两侧向脸中线做局部挤压形变。"""

from __future__ import annotations

import numpy as np

from ..cv.analyzer import JAW_LEFT, JAW_RIGHT
from ..cv.warp import warp_by_points
from .base import BaseTool, ToolContext, ToolParameter


class SlimFaceTool(BaseTool):
    name = "slim_face"
    description = "瘦脸：让脸型更窄、下颌线更精致。会先检测人脸关键点再作用。"
    parameters = [
        ToolParameter(
            "strength",
            "瘦脸强度，0 无效果，1 最强。建议 0.3~0.6，过高会显得不自然。",
            "number",
            minimum=0.0,
            maximum=1.0,
            default=0.4,
        )
    ]

    def apply(self, image: np.ndarray, ctx: ToolContext, strength: float = 0.4) -> np.ndarray:
        if strength <= 0:
            return image.copy()
        analysis = ctx.analyze(image)
        out = image
        for face in analysis.faces:
            if face.landmarks is None:
                continue
            lm = face.landmarks
            cx = face.center[0]
            src: list[tuple[float, float]] = []
            disp: list[tuple[float, float]] = []
            for idx in JAW_LEFT:
                x, y = float(lm[idx][0]), float(lm[idx][1])
                if x < cx:
                    src.append((x, y))
                    disp.append(((cx - x) * 0.14 * strength, 0.0))
            for idx in JAW_RIGHT:
                x, y = float(lm[idx][0]), float(lm[idx][1])
                if x > cx:
                    src.append((x, y))
                    disp.append((-(x - cx) * 0.14 * strength, 0.0))
            radius = max(face.box[2] * 0.40, 20.0)
            out = warp_by_points(out, src, disp, radius)
        return out
