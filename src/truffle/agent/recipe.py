"""风格配方学习（第一阶段：目标分布 + 最近邻配方）。

不训练大模型，也不上传用户数据：
1. 从好看图片提取指标分布，生成/校准 StyleProfile 的目标区间；
2. 用求解器把源图调到风格目标，记录 (指标 → 参数)；
3. 运行时用最近邻配方给求解器一个更好的初值。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..config import config_dir
from ..cv.analyzer import Analyzer
from ..cv.metrics import measure
from ..tools.registry import ToolRegistry
from .solver import ParamSolver
from .style import StyleProfile

_FEATURE_KEYS = (
    "tone.ev", "tone.contrast", "color.sat", "color.skin_L",
    "color.skin_a", "quality.sharp", "quality.noise",
    "style_vec.warmth", "style_vec.airy", "style_vec.contrast",
    "style_vec.glow", "style_vec.cool_shadow", "style_vec.film",
)


def _get(state: dict[str, Any], path: str) -> float:
    node: Any = state
    for part in path.split("."):
        if not isinstance(node, dict):
            return 0.0
        node = node.get(part, 0.0)
    try:
        return float(node)
    except (TypeError, ValueError):
        return 0.0


def feature_vector(state: dict[str, Any]) -> list[float]:
    return [_get(state, key) for key in _FEATURE_KEYS]


def recipe_dir() -> Path:
    path = config_dir() / "recipes"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class RecipeSample:
    style_id: str
    features: list[float]
    jobs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "features": [round(v, 5) for v in self.features],
            "jobs": [[name, params] for name, params in self.jobs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecipeSample":
        jobs = []
        for item in data.get("jobs", []):
            if isinstance(item, list) and len(item) == 2 and isinstance(item[1], dict):
                jobs.append((str(item[0]), item[1]))
        return cls(
            style_id=str(data.get("style_id", "")),
            features=[float(v) for v in data.get("features", [])],
            jobs=jobs,
        )


class RecipeMemory:
    def __init__(self, style_id: str, path: str | Path | None = None) -> None:
        self.style_id = style_id
        self.samples: list[RecipeSample] = []
        self.path = Path(path) if path else recipe_dir() / f"{style_id}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.samples = [RecipeSample.from_dict(item) for item in data.get("samples", [])]
        except (OSError, json.JSONDecodeError):
            self.samples = []

    def save(self) -> None:
        self.path.write_text(
            json.dumps(
                {"style_id": self.style_id, "samples": [s.to_dict() for s in self.samples]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def add(self, state: dict[str, Any], jobs: list[tuple[str, dict[str, Any]]]) -> None:
        if not jobs:
            return
        self.samples.append(RecipeSample(self.style_id, feature_vector(state), jobs))
        self.samples = self.samples[-500:]
        self.save()

    def nearest(self, state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        if not self.samples:
            return []
        target = feature_vector(state)
        best = min(
            self.samples,
            key=lambda sample: math.dist(target, sample.features) if len(sample.features) == len(target) else float("inf"),
        )
        return list(best.jobs)

    def train(self, prefer_gbdt: bool = True) -> "RecipeModel":
        return train_recipe_model(self, prefer_gbdt=prefer_gbdt)


@dataclass
class RecipeModel:
    """指标 → 参数配方模型。有 sklearn 时用 GBDT，否则用闭式岭回归。"""

    style_id: str
    kind: str = "ridge"
    features: list[str] = field(default_factory=lambda: list(_FEATURE_KEYS))
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    _gbdt: dict[str, Any] = field(default_factory=dict, repr=False)

    def predict(self, state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        x = np.asarray(feature_vector(state), dtype=np.float64)
        grouped: dict[str, dict[str, Any]] = {}
        for key, meta in self.targets.items():
            tool = str(meta["tool"])
            param = str(meta["param"])
            if key in self._gbdt:
                try:
                    value = float(self._gbdt[key].predict(x.reshape(1, -1))[0])
                except Exception:
                    value = float(np.dot(x, meta.get("coef", [])) + float(meta.get("intercept", 0.0)))
            else:
                coef = np.asarray(meta.get("coef", []), dtype=np.float64)
                value = float(np.dot(x, coef) + float(meta.get("intercept", 0.0)))
            if abs(value) < 0.02:
                continue
            grouped.setdefault(tool, {})[param] = round(value, 4)
        return [(tool, params) for tool, params in grouped.items() if params]

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else recipe_dir() / f"{self.style_id}_model.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        # GBDT 对象不序列化；系数始终保存，保证可回退
        target.write_text(
            json.dumps(
                {
                    "style_id": self.style_id,
                    "kind": self.kind,
                    "features": self.features,
                    "targets": self.targets,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(cls, path: str | Path) -> "RecipeModel":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            style_id=str(data.get("style_id", "")),
            kind=str(data.get("kind", "ridge")),
            features=list(data.get("features", _FEATURE_KEYS)),
            targets=dict(data.get("targets", {})),
        )


def _ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float = 1.0) -> tuple[np.ndarray, float]:
    n, d = x.shape
    if n == 0:
        return np.zeros(d, dtype=np.float64), 0.0
    x_design = np.hstack([x, np.ones((n, 1), dtype=np.float64)])
    reg = np.eye(d + 1, dtype=np.float64) * alpha
    reg[-1, -1] = 0.0
    try:
        coef = np.linalg.solve(x_design.T @ x_design + reg, x_design.T @ y)
    except np.linalg.LinAlgError:
        coef = np.linalg.lstsq(x_design, y, rcond=None)[0]
    return coef[:-1], float(coef[-1])


def train_recipe_model(memory: RecipeMemory, prefer_gbdt: bool = True) -> RecipeModel:
    if not memory.samples:
        return RecipeModel(style_id=memory.style_id)
    x = np.asarray([sample.features for sample in memory.samples], dtype=np.float64)
    keys: dict[str, tuple[str, str]] = {}
    for sample in memory.samples:
        for tool, params in sample.jobs:
            for param, value in params.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    keys[f"{tool}.{param}"] = (tool, param)
    model = RecipeModel(style_id=memory.style_id)
    gbdt = None
    if prefer_gbdt:
        try:
            from sklearn.ensemble import GradientBoostingRegressor  # type: ignore

            gbdt = GradientBoostingRegressor(random_state=0, n_estimators=60, max_depth=2)
            model.kind = "gbdt"
        except Exception:
            gbdt = None
    for key, (tool, param) in keys.items():
        y = np.asarray(
            [
                float(dict(sample.jobs).get(tool, {}).get(param, 0.0))
                for sample in memory.samples
            ],
            dtype=np.float64,
        )
        coef, intercept = _ridge_fit(x, y)
        model.targets[key] = {
            "tool": tool,
            "param": param,
            "coef": [round(float(v), 6) for v in coef],
            "intercept": round(intercept, 6),
        }
        if gbdt is not None:
            try:
                fitted = gbdt.fit(x, y)
                model._gbdt[key] = fitted
            except Exception:
                model.kind = "ridge"
    return model


def learn_targets(
    images: list[np.ndarray],
    analyzer: Analyzer,
    *,
    style_id: str,
    name: str,
    description: str,
    low: float = 0.15,
    high: float = 0.85,
    weights: dict[str, float] | None = None,
) -> StyleProfile:
    """从一组好看图片学习目标区间（分位数）。"""
    states = [measure(image, analyzer, body=False) for image in images]
    targets: dict[str, tuple[float, float]] = {}
    for key in _FEATURE_KEYS:
        values = [_get(state, key) for state in states]
        if not values:
            continue
        lo = float(np.quantile(values, low))
        hi = float(np.quantile(values, high))
        if hi <= lo:
            hi = lo + 0.01
        targets[key] = (round(lo, 4), round(hi, 4))
    return StyleProfile(
        id=style_id,
        name=name,
        description=description,
        targets=targets,
        weights=weights or {},
    )


def mine_recipes(
    images: list[np.ndarray],
    registry: ToolRegistry,
    analyzer: Analyzer,
    profile: StyleProfile,
    *,
    max_images: int = 50,
) -> RecipeMemory:
    """用求解器把源图调到风格目标，记录参数配方（自监督）。"""
    memory = RecipeMemory(profile.id)
    solver = ParamSolver(registry, analyzer, preview_max=512, max_iterations=1, max_evaluations=8)
    for image in images[:max_images]:
        state = measure(image, analyzer, body=False)
        result = solver.solve(image, profile, state)
        if result.jobs:
            memory.add(state, result.jobs)
    return memory
