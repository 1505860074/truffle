"""局部蒙版：矩形、椭圆、径向、线性渐变。

参数使用 0~1 归一化坐标，与分辨率无关；工具内部再按图像尺寸放大。
"""

from __future__ import annotations

import cv2
import numpy as np


def _px(value: float, size: int) -> int:
    return int(round(float(value) * size))


def rect_mask(
    height: int, width: int, x1: float, y1: float, x2: float, y2: float,
    feather: float = 0.0,
) -> np.ndarray:
    xa, xb = sorted((_px(x1, width), _px(x2, width)))
    ya, yb = sorted((_px(y1, height), _px(y2, height)))
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(mask, (xa, ya), (xb, yb), 255, -1)
    return _feather(mask, feather, width, height)


def ellipse_mask(
    height: int, width: int, x1: float, y1: float, x2: float, y2: float,
    feather: float = 0.0,
) -> np.ndarray:
    xa, xb = sorted((_px(x1, width), _px(x2, width)))
    ya, yb = sorted((_px(y1, height), _px(y2, height)))
    cx, cy = (xa + xb) // 2, (ya + yb) // 2
    rx, ry = max(1, abs(xb - xa) // 2), max(1, abs(yb - ya) // 2)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.ellipse(mask, (cx, cy), (rx, ry), 0, 0, 360, 255, -1)
    return _feather(mask, feather, width, height)


def radial_mask(
    height: int, width: int, x1: float, y1: float, x2: float, y2: float,
    feather: float = 0.0, invert: bool = False,
) -> np.ndarray:
    cx, cy = _px(x1, width), _px(y1, height)
    rx = max(1, abs(_px(x2, width) - cx))
    ry = max(1, abs(_px(y2, height) - cy))
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    soft = max(0.001, float(feather))
    mask = np.clip((1.0 - dist) / soft, 0.0, 1.0)
    if invert:
        mask = 1.0 - mask
    return (mask * 255).astype(np.uint8)


def linear_mask(
    height: int, width: int, x1: float, y1: float, x2: float, y2: float,
    feather: float = 0.2, invert: bool = False,
) -> np.ndarray:
    p1 = np.array([_px(x1, width), _px(y1, height)], dtype=np.float32)
    p2 = np.array([_px(x2, width), _px(y2, height)], dtype=np.float32)
    vec = p2 - p1
    length = float(np.linalg.norm(vec))
    if length < 1e-3:
        return np.full((height, width), 255, dtype=np.uint8)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    proj = ((xx - p1[0]) * vec[0] + (yy - p1[1]) * vec[1]) / (length * length)
    proj = np.clip(proj, 0.0, 1.0)
    soft = max(0.001, float(feather))
    mask = np.clip((proj - 0.5) / soft + 0.5, 0.0, 1.0)
    if invert:
        mask = 1.0 - mask
    return (mask * 255).astype(np.uint8)


def mask_from_params(height: int, width: int, params: dict) -> np.ndarray:
    shape = str(params.get("shape", "rect"))
    x1 = float(params.get("x1", 0.2))
    y1 = float(params.get("y1", 0.2))
    x2 = float(params.get("x2", 0.8))
    y2 = float(params.get("y2", 0.8))
    feather = float(params.get("feather", 0.15))
    invert = bool(params.get("invert", False))
    if shape == "ellipse":
        mask = ellipse_mask(height, width, x1, y1, x2, y2, feather)
        return 255 - mask if invert else mask
    if shape == "radial":
        return radial_mask(height, width, x1, y1, x2, y2, feather, invert)
    if shape == "linear":
        return linear_mask(height, width, x1, y1, x2, y2, feather, invert)
    mask = rect_mask(height, width, x1, y1, x2, y2, feather)
    return 255 - mask if invert else mask


def _feather(mask: np.ndarray, feather: float, width: int, height: int) -> np.ndarray:
    if feather <= 0:
        return mask
    sigma = max(0.5, float(feather) * max(width, height) * 0.5)
    return cv2.GaussianBlur(mask, (0, 0), sigma)


def apply_mask(image: np.ndarray, adjusted: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if mask.shape[:2] != image.shape[:2]:
        mask = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_LINEAR)
    alpha = (mask.astype(np.float32) / 255.0)[..., None]
    out = image.astype(np.float32) * (1 - alpha) + adjusted.astype(np.float32) * alpha
    return np.clip(out, 0, 255).astype(np.uint8)
