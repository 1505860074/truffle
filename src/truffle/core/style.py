"""风格匹配：把图片分析成「参数化风格画像」，再据此推导修正参数。

思路（不是无脑套同一组参数）：
- 对模板图与目标图各自测量亮度、对比、饱和、暖度、色调、清晰度等指标；
- 求两者差值，映射成一组工具参数，让目标图**向模板的风格靠拢**；
- 因每张图的基础不同，得到的修正量也不同，最终风格更一致。
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np


def profile(image: np.ndarray) -> dict[str, float]:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0] / 255.0
    a = lab[..., 1] - 128.0
    b = lab[..., 2] - 128.0
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    S = hsv[..., 1] / 255.0
    hue_rad = np.deg2rad(hsv[..., 0] * 2.0)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    w = S.ravel()
    if w.sum() > 1e-6:
        ang = hue_rad.ravel()
        hue = float(math.degrees(math.atan2((np.sin(ang) * w).sum(), (np.cos(ang) * w).sum())) % 360.0)
    else:
        hue = 0.0

    return {
        "brightness": float(L.mean()),
        "contrast": float(L.std()),
        "saturation": float(S.mean()),
        "warmth": float(b.mean()),   # 正=偏黄暖，负=偏蓝冷
        "tint": float(a.mean()),     # 正=偏红，负=偏绿
        "hue": hue,
        "clarity": float(cv2.Laplacian(gray, cv2.CV_32F).var()),
    }


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _hue_delta(src_hue: float, dst_hue: float) -> float:
    d = (src_hue - dst_hue + 180.0) % 360.0 - 180.0
    return d / 180.0


def match_params(src: dict[str, float], dst: dict[str, float]) -> list[tuple[str, dict[str, Any]]]:
    """由模板画像 src 与目标画像 dst 推导一组修正参数。"""
    jobs: list[tuple[str, dict[str, Any]]] = []

    brightness = _clamp((src["brightness"] - dst["brightness"]) * 2.0)
    contrast = _clamp((src["contrast"] - dst["contrast"]) * 2.5)
    saturation = _clamp((src["saturation"] - dst["saturation"]) * 2.0)
    if abs(brightness) > 0.02 or abs(contrast) > 0.02 or abs(saturation) > 0.02:
        jobs.append(("color_adjust", {
            "brightness": round(brightness, 3),
            "contrast": round(contrast, 3),
            "saturation": round(saturation, 3),
        }))

    temperature = _clamp((src["warmth"] - dst["warmth"]) / 40.0)
    tint = _clamp((src["tint"] - dst["tint"]) / 25.0)
    if abs(temperature) > 0.02 or abs(tint) > 0.02:
        jobs.append(("color_temp", {
            "temperature": round(temperature, 3), "tint": round(tint, 3),
        }))

    hue = _clamp(_hue_delta(src["hue"], dst["hue"]))
    if abs(hue) > 0.03:
        jobs.append(("hsl", {"hue": round(hue, 3), "saturation": 0.0, "lightness": 0.0}))

    ratio = (src["clarity"] + 1e-6) / (dst["clarity"] + 1e-6)
    clarity = _clamp(math.log2(ratio) * 0.25)
    if abs(clarity) > 0.03:
        jobs.append(("sharpen_clarity", {"sharpen": 0.0, "clarity": round(clarity, 3)}))

    return jobs
