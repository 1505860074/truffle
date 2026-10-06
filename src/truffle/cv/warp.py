"""局部形变原语：基于控制点的位移场 + remap。

思路类似 Photoshop 的「液化」：给定若干源点和目标点，每个像素的位移是
各控制点位移按「到控制点距离」加权的叠加，用高斯式权重保证过渡平滑。
"""

from __future__ import annotations

import cv2
import numpy as np


def warp_by_points(
    image: np.ndarray,
    src_points: list[tuple[float, float]],
    displacements: list[tuple[float, float]],
    radius: float,
) -> np.ndarray:
    """对图像做局部形变。

    Args:
        image: BGR 图像。
        src_points: 控制点坐标 [(x, y), ...]。
        displacements: 与 src_points 对应的位移 (dx, dy)。
        radius: 影响半径（像素），超出该距离的控制点不再影响。
    """
    if not src_points:
        return image.copy()

    h, w = image.shape[:2]
    grid_x, grid_y = np.meshgrid(
        np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32)
    )

    dx = np.zeros((h, w), dtype=np.float32)
    dy = np.zeros((h, w), dtype=np.float32)

    for (sx, sy), (ddx, ddy) in zip(src_points, displacements):
        dist = np.sqrt((grid_x - sx) ** 2 + (grid_y - sy) ** 2)
        weight = np.clip(1.0 - dist / radius, 0.0, 1.0) ** 2
        dx += ddx * weight
        dy += ddy * weight

    map_x = (grid_x + dx).astype(np.float32)
    map_y = (grid_y + dy).astype(np.float32)
    return cv2.remap(
        image, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )
