"""一键风格离线评估：给风格迭代提供可重复的基准。

不调用大模型，只跑「测量 → 求解 → 评审」，输出可比较的指标。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..cv.analyzer import Analyzer
from ..cv.metrics import measure
from ..tools.registry import ToolRegistry
from .aesthetic import AestheticPrior
from .critic import evaluate
from .solver import ParamSolver
from .style import StyleProfile, style_distance


@dataclass
class ImageEvaluation:
    path: str
    style_distance_before: float
    style_distance_after: float
    naturalness: float
    aesthetic_score: float
    jobs: int
    artifacts: int
    seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "style_distance_before": round(self.style_distance_before, 4),
            "style_distance_after": round(self.style_distance_after, 4),
            "naturalness": round(self.naturalness, 4),
            "aesthetic_score": round(self.aesthetic_score, 4),
            "jobs": self.jobs,
            "artifacts": self.artifacts,
            "seconds": round(self.seconds, 3),
        }


def evaluate_image(
    image: np.ndarray,
    registry: ToolRegistry,
    analyzer: Analyzer,
    profile: StyleProfile,
    *,
    path: str = "",
    solver: ParamSolver | None = None,
    aesthetic: AestheticPrior | None = None,
) -> ImageEvaluation:
    solver = solver or ParamSolver(registry, analyzer)
    aesthetic = aesthetic or AestheticPrior()
    started = time.perf_counter()
    before = measure(image, analyzer)
    before_distance, _ = style_distance(before, profile)
    result = solver.solve(image, profile, before)
    after_image = _render(registry, analyzer, image, result.jobs)
    after = measure(after_image, analyzer)
    after_distance, _ = style_distance(after, profile)
    aesthetic_result = aesthetic.score(after_image, after)
    critique = evaluate(before, after, profile, result.jobs, result.naturalness, aesthetic_result)
    return ImageEvaluation(
        path=path,
        style_distance_before=before_distance,
        style_distance_after=after_distance,
        naturalness=result.naturalness,
        aesthetic_score=float(aesthetic_result.get("score", 0.0)),
        jobs=len(result.jobs),
        artifacts=len(critique.issues),
        seconds=time.perf_counter() - started,
    )


def evaluate_paths(
    paths: list[str | Path],
    registry: ToolRegistry,
    analyzer: Analyzer,
    profile: StyleProfile,
) -> list[ImageEvaluation]:
    solver = ParamSolver(registry, analyzer)
    aesthetic = AestheticPrior()
    out: list[ImageEvaluation] = []
    for path in paths:
        data = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            continue
        out.append(
            evaluate_image(
                image, registry, analyzer, profile,
                path=str(path), solver=solver, aesthetic=aesthetic,
            )
        )
    return out


def summarize(results: list[ImageEvaluation]) -> dict[str, float]:
    if not results:
        return {}
    return {
        "images": float(len(results)),
        "style_distance_before": float(np.mean([r.style_distance_before for r in results])),
        "style_distance_after": float(np.mean([r.style_distance_after for r in results])),
        "naturalness": float(np.mean([r.naturalness for r in results])),
        "aesthetic_score": float(np.mean([r.aesthetic_score for r in results])),
        "artifacts": float(np.mean([r.artifacts for r in results])),
        "seconds": float(np.mean([r.seconds for r in results])),
    }


def _render(registry: ToolRegistry, analyzer: Analyzer, image: np.ndarray, jobs) -> np.ndarray:
    if not jobs:
        return image
    from ..tools.base import ToolContext
    from ..tools.pipeline import render_pipeline

    return render_pipeline(registry, analyzer, image, jobs)
