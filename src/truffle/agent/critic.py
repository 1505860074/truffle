"""评审器：判断一次编辑是否达标、是否过头、是否有伪影。

不调用 LLM，只依赖指标与规则。结果回填给模型，驱动下一轮修正。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .style import StyleProfile, style_distance


@dataclass
class Critique:
    ok: bool
    style_distance: float
    naturalness: float
    issues: list[str] = field(default_factory=list)
    deltas: dict[str, float] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "style_distance": round(self.style_distance, 4),
            "naturalness": round(self.naturalness, 4),
            "issues": list(self.issues),
            "deltas": dict(self.deltas),
            "suggestions": list(self.suggestions),
        }

    def text(self) -> str:
        import json

        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


def evaluate(
    before: dict[str, Any],
    after: dict[str, Any],
    profile: StyleProfile,
    jobs: list[tuple[str, dict[str, Any]]] | None = None,
    naturalness: float = 1.0,
) -> Critique:
    distance, deltas = style_distance(after, profile)
    issues: list[str] = []
    suggestions: list[str] = []

    bq = before.get("quality", {})
    aq = after.get("quality", {})
    clip_delta = float(aq.get("clip_hi", 0.0)) - float(bq.get("clip_hi", 0.0))
    if clip_delta > 0.01:
        issues.append("highlight_clipping")
        suggestions.append("降低高光/曝光")
    if float(aq.get("noise", 0.0)) - float(bq.get("noise", 0.0)) > 0.15:
        issues.append("noise_increase")
        suggestions.append("降低锐化或增加降噪")
    if float(bq.get("sharp", 0.0)) - float(aq.get("sharp", 0.0)) > 0.25:
        issues.append("sharpness_loss")
        suggestions.append("减少磨皮/降低降噪")

    b_texture = _face_skin(before, "texture")
    a_texture = _face_skin(after, "texture")
    if b_texture is not None and a_texture is not None and b_texture > 0.05:
        if a_texture / max(b_texture, 1e-6) < 0.55:
            issues.append("skin_texture_loss")
            suggestions.append("降低磨皮强度")

    if float(after.get("color", {}).get("sat", 0.0)) > 0.72:
        issues.append("oversaturation")
        suggestions.append("降低饱和度")
    if naturalness < 0.65:
        issues.append("over_edited")
        suggestions.append("整体强度过高")

    if distance > 0.25:
        suggestions.append("继续向风格目标靠拢")
    ok = distance <= 0.22 and naturalness >= 0.65 and not issues
    return Critique(
        ok=ok,
        style_distance=distance,
        naturalness=naturalness,
        issues=issues,
        deltas=deltas,
        suggestions=suggestions,
    )


def _face_skin(state: dict[str, Any], key: str) -> float | None:
    values = [
        item.get("skin", {}).get(key)
        for item in state.get("faces", [])
        if isinstance(item, dict) and item.get("skin", {}).get(key) is not None
    ]
    return float(sum(values) / len(values)) if values else None
