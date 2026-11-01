"""瘦脸：沿下颌/脸颊向脸中线做平滑挤压（高斯衰减，过渡自然，少拖背景）。"""

from __future__ import annotations

import numpy as np

from ..cv.analyzer import JAW_LEFT, JAW_RIGHT
from ..cv.warp import warp_by_points
from .base import BaseTool, ToolContext, ToolParameter


def _with_midpoints(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """在相邻控制点间补中点，让形变更顺滑。"""
    out = list(points)
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        out.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0))
    return out


class SlimFaceTool(BaseTool):
    name = "slim_face"
    description = "瘦脸：让脸型更窄、下颌线更精致，过渡自然。会先检测人脸关键点再作用。"
    parameters = [
        ToolParameter("strength", "瘦脸强度，建议 0.3~0.6，过高会不自然。", "number", 0.0, 1.0, 0.4),
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
            for indices, is_left in ((JAW_LEFT, True), (JAW_RIGHT, False)):
                pts = _with_midpoints([(float(lm[i][0]), float(lm[i][1])) for i in indices])
                for x, y in pts:
                    if is_left and x < cx:
                        src.append((x, y))
                        disp.append(((cx - x) * 0.13 * strength, 0.0))
                    elif (not is_left) and x > cx:
                        src.append((x, y))
                        disp.append((-(x - cx) * 0.13 * strength, 0.0))
            radius = max(face.box[2] * 0.42, 24.0)
            out = warp_by_points(out, src, disp, radius, falloff="gauss")
        return out
