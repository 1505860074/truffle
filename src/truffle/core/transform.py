"""自由变换原语：四点透视变换（移动/缩放/旋转/斜切/透视/翻转）。

坐标系：
- 源矩形 `src_rect = (x, y, w, h)` 与目标四边形 `dst_quad`
  （TL, TR, BR, BL，图像绝对坐标）；
- 变换矩阵由「源矩形四角 → 目标四角」求得，可表达任意透视。
"""

from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np

from .layers import alpha_over, ensure_bgra


Point = tuple[float, float]
Quad = list[Point]


def quad_from_rect(rect: tuple[int, int, int, int]) -> Quad:
    x, y, w, h = rect
    return [(float(x), float(y)), (float(x + w), float(y)),
            (float(x + w), float(y + h)), (float(x), float(y + h))]


def rect_from_quad(quad: Iterable[Point]) -> tuple[int, int, int, int]:
    pts = np.asarray(list(quad), dtype=np.float32)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    return int(np.floor(x0)), int(np.floor(y0)), max(1, int(np.ceil(x1 - x0))), max(1, int(np.ceil(y1 - y0)))


def center_of(quad: Iterable[Point]) -> Point:
    pts = np.asarray(list(quad), dtype=np.float32)
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def homography(src_quad: Iterable[Point], dst_quad: Iterable[Point]) -> np.ndarray:
    src = np.asarray(list(src_quad), dtype=np.float32)
    dst = np.asarray(list(dst_quad), dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def warp_full(
    patch_bgra: np.ndarray,
    src_quad: Iterable[Point],
    dst_quad: Iterable[Point],
    canvas_w: int,
    canvas_h: int,
) -> np.ndarray:
    """把补丁透视变换到整张画布，画布外透明。"""
    patch = ensure_bgra(patch_bgra)
    h = homography(src_quad, dst_quad)
    return cv2.warpPerspective(
        patch, h, (int(canvas_w), int(canvas_h)),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


def warp_roi(
    patch_bgra: np.ndarray,
    src_quad: Iterable[Point],
    dst_quad: Iterable[Point],
    canvas_w: int,
    canvas_h: int,
    margin: int = 2,
) -> tuple[np.ndarray, int, int]:
    """把补丁透视变换到目标包围盒大小的 ROI，返回 (ROI, x0, y0)。

    用于拖拽时的实时预览，避免每次都对整张大图做 warp。
    """
    patch = ensure_bgra(patch_bgra)
    x, y, w, h = rect_from_quad(dst_quad)
    x0 = max(0, x - margin)
    y0 = max(0, y - margin)
    x1 = min(int(canvas_w), x + w + margin)
    y1 = min(int(canvas_h), y + h + margin)
    if x1 <= x0 or y1 <= y0:
        return np.zeros((1, 1, 4), dtype=np.uint8), x0, y0
    matrix = homography(src_quad, dst_quad)
    shift = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], dtype=np.float64)
    local = shift @ matrix
    roi = cv2.warpPerspective(
        patch, local, (x1 - x0, y1 - y0),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    return roi, x0, y0


def _rect_clear_mask(shape: tuple[int, int], rect: tuple[int, int, int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    x, y, w, h = rect
    H, W = shape
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, int(x + w)), min(H, int(y + h))
    if x1 > x0 and y1 > y0:
        mask[y0:y1, x0:x1] = 255
    return mask


def transform_layer(image_bgra: np.ndarray, src_rect: tuple[int, int, int, int],
                    dst_quad: Iterable[Point], selection: np.ndarray | None = None) -> np.ndarray:
    """对图层像素做自由变换。

    - `selection` 为 None：变换 `src_rect` 内的整块像素；
    - 提供 `selection`：只变换选区内的像素，其余像素保持原样。
    """
    layer = ensure_bgra(image_bgra)
    H, W = layer.shape[:2]
    x, y, w, h = [int(v) for v in src_rect]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return layer.copy()
    patch = layer[y0:y1, x0:x1].copy()

    if selection is not None and selection.shape[:2] == (H, W):
        sel = selection[y0:y1, x0:x1].astype(np.float32) / 255.0
        patch[..., 3] = np.clip(patch[..., 3].astype(np.float32) * sel, 0, 255).astype(np.uint8)
        clear = selection
    else:
        clear = _rect_clear_mask((H, W), (x0, y0, x1 - x0, y1 - y0))

    local_quad = [(0.0, 0.0), (float(x1 - x0), 0.0),
                  (float(x1 - x0), float(y1 - y0)), (0.0, float(y1 - y0))]
    warped = warp_full(patch, local_quad, dst_quad, W, H)

    base = layer.copy()
    keep = 1.0 - clear.astype(np.float32) / 255.0
    base[..., 3] = np.clip(base[..., 3].astype(np.float32) * keep, 0, 255).astype(np.uint8)
    return alpha_over(base, warped)


def flip_quad(quad: Iterable[Point], horizontal: bool = True,
              vertical: bool = False, center: Point | None = None) -> Quad:
    pts = [list(p) for p in quad]
    cx, cy = center if center is not None else center_of(pts)
    for p in pts:
        if horizontal:
            p[0] = 2.0 * cx - p[0]
        if vertical:
            p[1] = 2.0 * cy - p[1]
    return [(float(x), float(y)) for x, y in pts]


def rotate_quad(quad: Iterable[Point], angle_deg: float, center: Point | None = None) -> Quad:
    pts = np.asarray(list(quad), dtype=np.float32)
    cx, cy = center if center is not None else center_of(pts)
    rad = np.deg2rad(float(angle_deg))
    cos, sin = np.cos(rad), np.sin(rad)
    x = pts[:, 0] - cx
    y = pts[:, 1] - cy
    out = np.stack([x * cos - y * sin + cx, x * sin + y * cos + cy], axis=1)
    return [(float(a), float(b)) for a, b in out]


def translate_quad(quad: Iterable[Point], dx: float, dy: float) -> Quad:
    return [(float(x + dx), float(y + dy)) for x, y in quad]


def scale_quad(quad: Iterable[Point], sx: float, sy: float, anchor: Point) -> Quad:
    ax, ay = anchor
    out: Quad = []
    for x, y in quad:
        out.append((float(ax + (x - ax) * sx), float(ay + (y - ay) * sy)))
    return out
