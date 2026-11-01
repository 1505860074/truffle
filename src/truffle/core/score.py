"""图片评分与自动调色。

- `score(image)`：基于亮度/对比/饱和/白平衡等指标，给出一组 0~100 的子分与总分；
- `auto_grade_jobs(image)`：把图片的指标「向理想值靠拢」，推导出一组调色参数
  （用于批量自动调色——每张图按自身基础算不同修正量，不是纯套同一组参数）。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .style import match_params, profile

# 理想画像（可调）
IDEAL = {
    "brightness": 0.55,   # 平均亮度
    "contrast": 0.20,     # 亮度标准差
    "saturation": 0.36,   # 平均饱和度
    "warmth": 0.0,        # 冷暖（LAB b 均值偏移）
    "tint": 0.0,          # 绿-品红（LAB a 均值偏移）
}


def _subscore(value: float, ideal: float, span: float) -> float:
    return max(0.0, 100.0 - abs(value - ideal) / span * 100.0)


def score(image: np.ndarray) -> dict[str, float]:
    p = profile(image)
    parts = {
        "exposure": _subscore(p["brightness"], IDEAL["brightness"], 0.35),
        "contrast": _subscore(p["contrast"], IDEAL["contrast"], 0.18),
        "saturation": _subscore(p["saturation"], IDEAL["saturation"], 0.35),
        "white_balance": _subscore(p["warmth"], IDEAL["warmth"], 25.0),
    }
    overall = sum(parts.values()) / len(parts)
    result = {"overall": round(overall, 1)}
    result.update({k: round(v, 1) for k, v in parts.items()})
    return result


def auto_grade_jobs(image: np.ndarray) -> list[tuple[str, dict[str, Any]]]:
    p = profile(image)
    ideal = dict(p)
    ideal.update(IDEAL)  # 色相/清晰度保持原样，只校正曝光/对比/饱和/白平衡
    return match_params(ideal, p)
