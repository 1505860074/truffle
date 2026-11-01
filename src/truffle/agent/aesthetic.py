"""美学弱先验 / 异常检测。

只作为辅助信号：判断过曝、欠曝、过灰、过饱和、噪点等明显问题，
不做最终“美丑裁决”。模型存在时用 ONNX，缺失时用规则回退。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..cv.metrics import measure
from ..cv.onnx_runtime import backend_name, load_session


class AestheticPrior:
    def __init__(self, model_path: str | Path | None = None) -> None:
        self.path = Path(model_path) if model_path else Path("models") / "aesthetic.onnx"
        self.session = load_session(self.path)
        self.backend = backend_name() if self.session is not None else "heuristic"

    @property
    def using_model(self) -> bool:
        return self.session is not None

    def score(self, image: np.ndarray, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = state or measure(image, body=False)
        issues = _issues(state)
        if self.session is not None:
            try:
                value = self._infer(image)
                return {
                    "score": round(float(np.clip(value, 0.0, 1.0)), 4),
                    "source": self.backend,
                    "issues": issues,
                }
            except Exception:
                pass
        return {
            "score": round(_heuristic_score(state), 4),
            "source": "heuristic",
            "issues": issues,
        }

    def _infer(self, image: np.ndarray) -> float:
        size = 224
        resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        blob = ((rgb - mean) / std).transpose(2, 0, 1)[None].astype(np.float32)
        name = self.session.get_inputs()[0].name
        output = np.asarray(self.session.run(None, {name: blob})[0]).reshape(-1)
        if output.size == 10:  # NIMA 分布，转期望分
            probs = _softmax(output)
            expected = float(np.sum(probs * np.arange(1, 11)))
            return (expected - 1.0) / 9.0
        return float(output[0])


def _softmax(values: np.ndarray) -> np.ndarray:
    values = values - np.max(values)
    exp = np.exp(values)
    return exp / max(1e-8, float(exp.sum()))


def _issues(state: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    tone = state.get("tone", {})
    color = state.get("color", {})
    quality = state.get("quality", {})
    if float(tone.get("clip_hi", 0.0)) > 0.02:
        issues.append("highlight_clipping")
    if float(tone.get("clip_lo", 0.0)) > 0.06:
        issues.append("shadow_crushed")
    if float(tone.get("contrast", 0.0)) < 0.12:
        issues.append("flat_contrast")
    if float(color.get("sat", 0.0)) > 0.72:
        issues.append("oversaturated")
    if float(color.get("sat", 0.0)) < 0.08:
        issues.append("desaturated")
    if float(quality.get("noise", 0.0)) > 0.35:
        issues.append("noisy")
    if float(quality.get("haze", 0.0)) > 0.55:
        issues.append("hazy")
    return issues


def _heuristic_score(state: dict[str, Any]) -> float:
    tone = state.get("tone", {})
    color = state.get("color", {})
    quality = state.get("quality", {})
    score = 0.72
    score -= float(tone.get("clip_hi", 0.0)) * 3.0
    score -= float(tone.get("clip_lo", 0.0)) * 2.0
    contrast = float(tone.get("contrast", 0.35))
    score -= max(0.0, 0.18 - contrast) * 1.5
    score -= max(0.0, contrast - 0.75) * 1.0
    sat = float(color.get("sat", 0.3))
    score -= max(0.0, sat - 0.65) * 1.8
    score -= max(0.0, 0.10 - sat) * 1.2
    score -= float(quality.get("noise", 0.0)) * 0.6
    score -= float(quality.get("haze", 0.0)) * 0.4
    return float(np.clip(score, 0.0, 1.0))
