"""成套图：项目级风格、基准指标、一致性检查与拼图预览。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..cv.metrics import measure
from ..cv.analyzer import Analyzer
from .style import StyleProfile, style_distance
from .solver import ParamSolver, SolveResult


@dataclass
class SeriesPlan:
    style_id: str
    consistency: float = 0.8
    baseline: dict[str, float] = field(default_factory=dict)
    images: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "consistency": self.consistency,
            "baseline": dict(self.baseline),
            "images": list(self.images),
        }


def _median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def plan_series(
    images: list[np.ndarray],
    analyzer: Analyzer,
    profile: StyleProfile,
    consistency: float = 0.8,
) -> SeriesPlan:
    """先测全项目基准，再给每张图记录与基准的偏差。"""
    consistency = max(0.0, min(1.0, float(consistency)))
    states = [measure(image, analyzer, body=False) for image in images]
    baseline = {
        "skin_L": _median([float(s.get("color", {}).get("skin_L", 0.0)) for s in states]) or 0.0,
        "contrast": _median([float(s.get("tone", {}).get("contrast", 0.0)) for s in states]) or 0.0,
        "sat": _median([float(s.get("color", {}).get("sat", 0.0)) for s in states]) or 0.0,
        "wb_k": _median([float(s.get("tone", {}).get("wb_k", 6500.0)) for s in states]) or 6500.0,
    }
    items = []
    for index, state in enumerate(states):
        delta = {
            "skin_L": round(float(state.get("color", {}).get("skin_L", 0.0)) - baseline["skin_L"], 4),
            "contrast": round(float(state.get("tone", {}).get("contrast", 0.0)) - baseline["contrast"], 4),
            "sat": round(float(state.get("color", {}).get("sat", 0.0)) - baseline["sat"], 4),
            "wb_k": round(float(state.get("tone", {}).get("wb_k", 6500.0)) - baseline["wb_k"], 1),
        }
        distance, _ = style_distance(state, profile)
        items.append({"index": index, "delta": delta, "style_distance": round(distance, 4)})
    return SeriesPlan(style_id=profile.id, consistency=consistency, baseline=baseline, images=items)


def profile_with_consistency(
    profile: StyleProfile,
    baseline: dict[str, float],
    consistency: float,
) -> StyleProfile:
    """把项目基准混入风格目标：一致性越高，越向项目基准收紧。"""
    consistency = max(0.0, min(1.0, float(consistency)))
    if consistency <= 0:
        return profile
    targets = dict(profile.all_targets())
    tolerance = {
        "color.skin_L": 0.02,
        "tone.contrast": 0.02,
        "color.sat": 0.02,
        "tone.wb_k": 120.0,
    }
    for key, base in baseline.items():
        path = {
            "skin_L": "color.skin_L",
            "contrast": "tone.contrast",
            "sat": "color.sat",
            "wb_k": "tone.wb_k",
        }.get(key)
        if path is None or path not in targets:
            continue
        lo, hi = targets[path]
        style_center = (lo + hi) / 2.0
        style_half = max(1e-6, (hi - lo) / 2.0)
        tol = tolerance.get(path, style_half * 0.2)
        center = consistency * float(base) + (1.0 - consistency) * style_center
        half = consistency * tol + (1.0 - consistency) * style_half
        targets[path] = (round(center - half, 4), round(center + half, 4))
    return StyleProfile(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        targets=targets,
        weights=dict(profile.weights),
        skin=dict(profile.skin),
        geometry=dict(profile.geometry),
        finish=dict(profile.finish),
        style_vec=dict(profile.style_vec),
    )


def solve_series(
    images: list[np.ndarray],
    registry,
    analyzer: Analyzer,
    profile: StyleProfile,
    *,
    consistency: float = 0.8,
    max_workers: int = 1,
) -> list[SolveResult]:
    """批量逐图求解。并发留给调用方/线程池，这里保持可测试的串行实现。"""
    solver = ParamSolver(registry, analyzer)
    plan = plan_series(images, analyzer, profile, consistency)
    adjusted = profile_with_consistency(profile, plan.baseline, consistency)
    results: list[SolveResult] = []
    for image in images:
        state = measure(image, analyzer)
        results.append(solver.solve(image, adjusted, state))
    return results


def contact_sheet(
    images: list[np.ndarray],
    columns: int = 3,
    cell: int = 360,
    labels: list[str] | None = None,
    center_text: str = "",
    center_avatar: np.ndarray | None = None,
) -> np.ndarray:
    """生成 N×N 拼图；图片不足时留白，中心可放文字或头像。"""
    columns = max(1, int(columns))
    rows = max(1, int(np.ceil(len(images) / columns)))
    canvas = np.full((rows * cell, columns * cell, 3), 28, dtype=np.uint8)
    for i, image in enumerate(images[: columns * rows]):
        r, c = divmod(i, columns)
        tile = _letterbox(image, cell, cell)
        canvas[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell] = tile
        if labels and i < len(labels):
            _put_label(canvas, labels[i], c * cell + 8, r * cell + 8)
    if center_text:
        _put_center_text(canvas, center_text)
    if center_avatar is not None:
        _put_avatar(canvas, center_avatar)
    return canvas


def _letterbox(image: np.ndarray, width: int, height: int) -> np.ndarray:
    h, w = image.shape[:2]
    if h <= 0 or w <= 0:
        return np.full((height, width, 3), 28, dtype=np.uint8)
    scale = min(width / w, height / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    small = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((height, width, 3), 28, dtype=np.uint8)
    x, y = (width - nw) // 2, (height - nh) // 2
    canvas[y:y + nh, x:x + nw] = small[..., :3]
    return canvas


def _put_label(canvas: np.ndarray, text: str, x: int, y: int) -> None:
    cv2.putText(
        canvas, text, (x, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
        (0, 0, 0), 2, cv2.LINE_AA,
    )
    cv2.putText(
        canvas, text, (x, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
        (255, 255, 255), 1, cv2.LINE_AA,
    )


def _put_center_text(canvas: np.ndarray, text: str) -> None:
    size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
    x = (canvas.shape[1] - size[0]) // 2
    y = (canvas.shape[0] + size[1]) // 2
    cv2.putText(
        canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
        (0, 0, 0), 4, cv2.LINE_AA,
    )
    cv2.putText(
        canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
        (255, 255, 255), 2, cv2.LINE_AA,
    )


def _put_avatar(canvas: np.ndarray, avatar: np.ndarray) -> None:
    size = min(canvas.shape[:2]) // 4
    if size <= 0:
        return
    avatar = _letterbox(avatar, size, size)
    cy, cx = canvas.shape[0] // 2, canvas.shape[1] // 2
    y0, x0 = cy - size // 2, cx - size // 2
    mask = np.zeros((size, size), dtype=np.uint8)
    cv2.circle(mask, (size // 2, size // 2), size // 2, 255, -1)
    alpha = (mask.astype(np.float32) / 255.0)[..., None]
    region = canvas[y0:y0 + size, x0:x0 + size]
    canvas[y0:y0 + size, x0:x0 + size] = (
        region.astype(np.float32) * (1 - alpha) + avatar.astype(np.float32) * alpha
    ).astype(np.uint8)


def export_batch(
    images: list[np.ndarray],
    out_dir: str | Path,
    prefix: str = "truffle",
    ext: str = ".jpg",
    quality: int = 92,
    long_side: int = 1080,
) -> list[Path]:
    """朋友圈批量导出：统一长边、JPEG 质量、序号命名。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)] if ext.lower() in (".jpg", ".jpeg") else []
    for i, image in enumerate(images, 1):
        resized = _resize_long_side(image, long_side)
        path = out / f"{prefix}_{i:02d}{ext}"
        ok, buf = cv2.imencode(ext, resized, params)
        if ok:
            buf.tofile(str(path))
            paths.append(path)
    return paths


def _resize_long_side(image: np.ndarray, long_side: int) -> np.ndarray:
    h, w = image.shape[:2]
    if long_side <= 0 or max(h, w) <= long_side:
        return image
    scale = long_side / float(max(h, w))
    return cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
