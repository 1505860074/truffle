"""选区原语：矩形 / 椭圆 / 套索 / 多边形 / 魔棒，羽化与布尔运算。

选区统一用 uint8 单通道掩膜表示（255=完全选中）。所有函数无状态。
"""

from __future__ import annotations

import cv2
import numpy as np

SELECTION_MODES: tuple[str, ...] = ("new", "add", "subtract", "intersect")
SELECTION_MODE_LABELS: dict[str, str] = {
    "new": "新建选区",
    "add": "添加到选区",
    "subtract": "从选区减去",
    "intersect": "与选区交叉",
}


def empty_mask(shape: tuple[int, int]) -> np.ndarray:
    return np.zeros((int(shape[0]), int(shape[1])), dtype=np.uint8)


def rect_mask(
    shape: tuple[int, int], x: int, y: int, w: int, h: int, feather: float = 0.0
) -> np.ndarray:
    mask = empty_mask(shape)
    H, W = mask.shape
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, int(x + w)), min(H, int(y + h))
    if x1 > x0 and y1 > y0:
        mask[y0:y1, x0:x1] = 255
    return feather_mask(mask, feather)


def ellipse_mask(
    shape: tuple[int, int], x: int, y: int, w: int, h: int, feather: float = 0.0
) -> np.ndarray:
    mask = empty_mask(shape)
    if w > 0 and h > 0:
        cv2.ellipse(
            mask,
            (int(round(x + w / 2)), int(round(y + h / 2))),
            (max(1, int(round(w / 2))), max(1, int(round(h / 2)))),
            0, 0, 360, 255, -1, lineType=cv2.LINE_AA,
        )
    return feather_mask(mask, feather)


def polygon_mask(
    shape: tuple[int, int], points: list[tuple[float, float]] | np.ndarray,
    feather: float = 0.0,
) -> np.ndarray:
    mask = empty_mask(shape)
    if points is None or len(points) < 3:
        return mask
    pts = np.asarray(points, dtype=np.int32).reshape(-1, 1, 2)
    cv2.fillPoly(mask, [pts], 255, lineType=cv2.LINE_AA)
    return feather_mask(mask, feather)


def wand_mask(
    image: np.ndarray,
    x: int,
    y: int,
    tolerance: int = 32,
    contiguous: bool = True,
    feather: float = 0.0,
) -> np.ndarray:
    """魔棒：按颜色相似度取选区。

    - contiguous=True 用洪水填充（只选连通区域）；
    - 否则按全局颜色差生成掩膜。
    """
    h, w = image.shape[:2]
    x = max(0, min(int(x), w - 1))
    y = max(0, min(int(y), h - 1))
    tol = max(0, int(tolerance))
    bgr = image[..., :3] if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if contiguous:
        mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        flags = 4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE
        diff = (tol, tol, tol)
        cv2.floodFill(
            bgr.copy(), mask, (x, y), 255, diff, diff, flags,
        )
        result = mask[1:-1, 1:-1].copy()
    else:
        seed = bgr[y, x].astype(np.int16)
        diff = np.abs(bgr.astype(np.int16) - seed[None, None, :]).max(axis=2)
        result = np.where(diff <= tol, 255, 0).astype(np.uint8)
    return feather_mask(result, feather)


def feather_mask(mask: np.ndarray, radius: float) -> np.ndarray:
    radius = float(radius)
    if radius <= 0.05:
        return mask
    sigma = max(0.1, radius / 3.0)
    return cv2.GaussianBlur(mask, (0, 0), sigma)


def combine(base: np.ndarray | None, shape: np.ndarray, mode: str) -> np.ndarray:
    if base is None or mode == "new":
        return shape.copy()
    if base.shape[:2] != shape.shape[:2]:
        shape = cv2.resize(shape, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_NEAREST)
    if mode == "add":
        return np.maximum(base, shape)
    if mode == "subtract":
        return cv2.subtract(base, shape)
    if mode == "intersect":
        return cv2.bitwise_and(base, shape)
    return shape.copy()


def invert(mask: np.ndarray) -> np.ndarray:
    return 255 - mask


def is_empty(mask: np.ndarray | None) -> bool:
    return mask is None or cv2.countNonZero(mask) == 0


def bounds(mask: np.ndarray | None) -> tuple[int, int, int, int] | None:
    if is_empty(mask):
        return None
    ys, xs = np.nonzero(mask > 0)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    return x0, y0, x1 - x0, y1 - y0


def contours(mask: np.ndarray | None, epsilon: float = 1.0) -> list[np.ndarray]:
    """返回简化后的轮廓（图像坐标），用于虚线框绘制。"""
    if is_empty(mask):
        return []
    found, _ = cv2.findContours((mask > 0).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out: list[np.ndarray] = []
    for contour in found:
        if cv2.contourArea(contour) < 1.5:
            continue
        approx = cv2.approxPolyDP(contour, max(0.1, float(epsilon)), True)
        if len(approx) >= 2:
            out.append(approx.reshape(-1, 2))
    return out


def multiply_alpha(image_bgra: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    """把选区作为额外 alpha 乘到 BGRA 图上（返回新图）。"""
    out = image_bgra.copy()
    if mask is not None and mask.shape[:2] == out.shape[:2]:
        a = out[..., 3].astype(np.float32) * (mask.astype(np.float32) / 255.0)
        out[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    return out


def clear_alpha(image_bgra: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    """清除选区内的 alpha（返回新图）。"""
    out = image_bgra.copy()
    if mask is not None and mask.shape[:2] == out.shape[:2]:
        a = out[..., 3].astype(np.float32) * (1.0 - mask.astype(np.float32) / 255.0)
        out[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    return out
