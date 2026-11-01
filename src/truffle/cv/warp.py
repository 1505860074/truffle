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
    falloff: str = "quad",
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
        if falloff == "gauss":
            weight = np.exp(-((dist / radius) ** 2) * 2.0)
        else:
            weight = np.clip(1.0 - dist / radius, 0.0, 1.0) ** 2
        dx += ddx * weight
        dy += ddy * weight

    map_x = (grid_x + dx).astype(np.float32)
    map_y = (grid_y + dy).astype(np.float32)
    return cv2.remap(
        image, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )


def _roi_bounds(h: int, w: int, cx: float, cy: float, radius: float, margin: int = 2):
    x0 = max(0, int(cx - radius - margin))
    x1 = min(w, int(cx + radius + margin + 1))
    y0 = max(0, int(cy - radius - margin))
    y1 = min(h, int(cy + radius + margin + 1))
    return x0, y0, x1, y1


def local_push(
    image: np.ndarray,
    cx: float,
    cy: float,
    dx: float,
    dy: float,
    radius: float,
    strength: float = 1.0,
) -> np.ndarray:
    """液化「推挤」：以 (cx,cy) 为圆心、radius 为半径，把像素沿 (dx,dy) 方向推移。

    只在局部 ROI 上 remap，保证交互时的实时性。内容随拖拽方向移动。
    """
    h, w = image.shape[:2]
    radius = max(float(radius), 1.0)
    x0, y0, x1, y1 = _roi_bounds(h, w, cx, cy, radius)
    if x1 <= x0 or y1 <= y0:
        return image
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    weight = np.clip(1.0 - dist / radius, 0.0, 1.0) ** 2 * strength
    map_x = xx - dx * weight
    map_y = yy - dy * weight
    out = image.copy()
    out[y0:y1, x0:x1] = cv2.remap(
        image[y0:y1, x0:x1], map_x - x0, map_y - y0,
        interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT,
    )
    return out


def distort(
    image: np.ndarray,
    mode: str,
    strength: float,
    cx: float,
    cy: float,
    radius: float,
) -> np.ndarray:
    """参数化扭曲：twirl（旋转）/ pinch（收拢）/ bulge（膨胀）/ stretch_h / stretch_v。"""
    h, w = image.shape[:2]
    radius = max(float(radius), 1.0)
    if mode in ("stretch_h", "stretch_v"):
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        factor = 1.0 + strength * 0.6
        if abs(factor) < 0.05:
            factor = 0.05 if factor >= 0 else -0.05
        if mode == "stretch_h":
            map_x = cx + (xx - cx) / factor
            map_y = yy
        else:
            map_x = xx
            map_y = cy + (yy - cy) / factor
        return cv2.remap(
            image, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
        )

    x0, y0, x1, y1 = _roi_bounds(h, w, cx, cy, radius)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dxr, dyr = xx - cx, yy - cy
    dist = np.sqrt(dxr ** 2 + dyr ** 2)
    weight = np.clip(1.0 - dist / radius, 0.0, 1.0)
    if mode == "twirl":
        ang = strength * np.pi * weight
        cos, sin = np.cos(ang), np.sin(ang)
        map_x = cx + dxr * cos - dyr * sin
        map_y = cy + dxr * sin + dyr * cos
    elif mode == "pinch":
        k = 1.0 - strength * weight
        map_x = cx + dxr * k
        map_y = cy + dyr * k
    elif mode == "bulge":
        k = 1.0 + strength * weight
        map_x = cx + dxr * k
        map_y = cy + dyr * k
    else:
        map_x, map_y = xx, yy
    out = image.copy()
    out[y0:y1, x0:x1] = cv2.remap(
        image[y0:y1, x0:x1], map_x - x0, map_y - y0,
        interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT,
    )
    return out
