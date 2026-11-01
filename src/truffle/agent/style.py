"""风格库与风格距离。

一个 StyleProfile 是一组目标区间，不是一张 LUT，也不是一句提示词。
LLM 选择风格，求解器把当前指标拉进目标区间。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable


@dataclass(frozen=True)
class StyleProfile:
    id: str
    name: str
    description: str
    targets: dict[str, tuple[float, float]] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    skin: dict[str, tuple[float, float]] = field(default_factory=dict)
    geometry: dict[str, tuple[float, float]] = field(default_factory=dict)
    makeup: dict[str, tuple[float, float]] = field(default_factory=dict)
    finish: dict[str, tuple[float, float]] = field(default_factory=dict)
    style_vec: dict[str, tuple[float, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "targets": {k: list(v) for k, v in self.targets.items()},
            "weights": dict(self.weights),
            "skin": {k: list(v) for k, v in self.skin.items()},
            "geometry": {k: list(v) for k, v in self.geometry.items()},
            "makeup": {k: list(v) for k, v in self.makeup.items()},
            "finish": {k: list(v) for k, v in self.finish.items()},
            "style_vec": {k: list(v) for k, v in self.style_vec.items()},
        }

    def all_targets(self) -> dict[str, tuple[float, float]]:
        out = dict(self.targets)
        out.update({f"skin.{k}": v for k, v in self.skin.items()})
        out.update({f"geometry.{k}": v for k, v in self.geometry.items()})
        out.update({f"makeup.{k}": v for k, v in self.makeup.items()})
        out.update({f"finish.{k}": v for k, v in self.finish.items()})
        out.update({f"style_vec.{k}": v for k, v in self.style_vec.items()})
        return out


PROFILES: dict[str, StyleProfile] = {
    "natural": StyleProfile(
        id="natural",
        name="自然",
        description="轻微提亮、自然肤色、保留皮肤纹理，适合日常记录。",
        targets={
            "tone.ev": (-0.10, 0.20),
            "tone.contrast": (0.28, 0.48),
            "tone.clip_hi": (0.0, 0.02),
            "color.sat": (0.24, 0.42),
            "color.skin_L": (0.58, 0.72),
            "quality.sharp": (0.32, 0.62),
            "quality.noise": (0.0, 0.28),
        },
        weights={"tone.ev": 1.0, "tone.contrast": 1.0, "color.sat": 1.0, "color.skin_L": 1.3},
        skin={"texture": (0.20, 0.55), "redness": (0.20, 0.48), "under_eye": (0.0, 0.35)},
        geometry={"face_wh": (1.20, 1.45), "jaw": (0.70, 0.90)},
        style_vec={"airy": (0.35, 0.65), "glow": (0.25, 0.60)},
    ),
    "tangshui": StyleProfile(
        id="tangshui",
        name="糖水通透",
        description="高光柔和、低对比、肤色偏暖、轻微发光，适合朋友圈人像。",
        targets={
            "tone.ev": (0.15, 0.50),
            "tone.contrast": (0.12, 0.32),
            "tone.shadow": (0.12, 0.30),
            "tone.clip_hi": (0.0, 0.015),
            "color.sat": (0.34, 0.55),
            "color.skin_L": (0.66, 0.80),
            "color.skin_a": (6.0, 20.0),
            "quality.sharp": (0.28, 0.55),
            "quality.noise": (0.0, 0.22),
        },
        weights={
            "tone.contrast": 1.4, "color.sat": 1.2, "color.skin_L": 1.5,
            "tone.clip_hi": 1.2, "style_vec.airy": 1.3, "style_vec.glow": 1.2,
        },
        skin={"texture": (0.15, 0.45), "redness": (0.18, 0.42), "under_eye": (0.0, 0.30)},
        geometry={"face_wh": (1.18, 1.38), "jaw": (0.68, 0.86)},
        finish={"vignette": (0.0, 0.15), "grain": (0.0, 0.06)},
        style_vec={"airy": (0.55, 0.85), "glow": (0.50, 0.85), "warmth": (0.45, 0.75)},
    ),
    "cold_white": StyleProfile(
        id="cold_white",
        name="冷白",
        description="偏冷、干净、低饱和高亮度，适合通勤和证件照。",
        targets={
            "tone.ev": (0.10, 0.40),
            "tone.contrast": (0.25, 0.45),
            "tone.wb_k": (4800, 6200),
            "color.sat": (0.16, 0.34),
            "color.skin_L": (0.68, 0.82),
            "color.skin_a": (-2.0, 12.0),
            "quality.sharp": (0.40, 0.70),
            "quality.noise": (0.0, 0.20),
        },
        weights={"tone.wb_k": 1.4, "color.skin_a": 1.4, "color.sat": 1.1, "color.skin_L": 1.3},
        skin={"texture": (0.18, 0.42), "redness": (0.10, 0.32)},
        style_vec={"cool_shadow": (0.55, 0.9), "warmth": (0.10, 0.42), "airy": (0.45, 0.75)},
    ),
    "warm_film": StyleProfile(
        id="warm_film",
        name="暖调胶片",
        description="偏暖、低对比、轻微褪色与颗粒，适合生活感照片。",
        targets={
            "tone.ev": (0.0, 0.35),
            "tone.contrast": (0.22, 0.42),
            "tone.wb_k": (6800, 8600),
            "color.sat": (0.18, 0.38),
            "color.skin_L": (0.55, 0.70),
            "quality.sharp": (0.20, 0.45),
            "quality.noise": (0.05, 0.35),
        },
        weights={"style_vec.warmth": 1.5, "style_vec.film": 1.4, "color.sat": 1.0},
        skin={"texture": (0.25, 0.60), "redness": (0.20, 0.45)},
        finish={"grain": (0.05, 0.18), "vignette": (0.05, 0.25)},
        style_vec={"warmth": (0.60, 0.90), "film": (0.55, 0.85), "contrast": (0.20, 0.40)},
    ),
    "night": StyleProfile(
        id="night",
        name="夜景氛围",
        description="压高光、提阴影、冷阴影、容忍噪点，保留夜景氛围。",
        targets={
            "tone.ev": (-0.30, 0.15),
            "tone.contrast": (0.35, 0.60),
            "tone.clip_hi": (0.0, 0.01),
            "tone.shadow": (0.15, 0.35),
            "color.sat": (0.20, 0.42),
            "quality.sharp": (0.25, 0.55),
            "quality.noise": (0.0, 0.45),
        },
        weights={"tone.clip_hi": 1.5, "tone.shadow": 1.2, "style_vec.cool_shadow": 1.2},
        finish={"vignette": (0.10, 0.35)},
        style_vec={"cool_shadow": (0.55, 0.90), "contrast": (0.40, 0.65)},
    ),
    "id_photo": StyleProfile(
        id="id_photo",
        name="证件照",
        description="曝光准确、肤色均匀、锐度适中、背景干净，避免过度美化。",
        targets={
            "tone.ev": (-0.05, 0.15),
            "tone.contrast": (0.32, 0.50),
            "tone.clip_hi": (0.0, 0.01),
            "color.sat": (0.20, 0.36),
            "color.skin_L": (0.62, 0.76),
            "color.skin_a": (4.0, 16.0),
            "quality.sharp": (0.45, 0.75),
            "quality.noise": (0.0, 0.18),
        },
        weights={"quality.sharp": 1.4, "tone.ev": 1.2, "color.skin_L": 1.2},
        skin={"texture": (0.25, 0.55), "redness": (0.18, 0.40), "under_eye": (0.0, 0.28)},
        geometry={"face_wh": (1.20, 1.42), "symmetry": (0.85, 1.0)},
        style_vec={"airy": (0.30, 0.60), "warmth": (0.30, 0.60)},
    ),
    "high_sat_low_contrast": StyleProfile(
        id="high_sat_low_contrast",
        name="高饱和低对比",
        description="色彩浓郁但反差柔和，接近社媒网感风格。",
        targets={
            "tone.ev": (0.10, 0.40),
            "tone.contrast": (0.10, 0.30),
            "color.sat": (0.48, 0.70),
            "color.skin_L": (0.62, 0.78),
            "quality.sharp": (0.28, 0.55),
        },
        weights={"color.sat": 1.6, "tone.contrast": 1.4, "style_vec.glow": 1.1},
        skin={"texture": (0.18, 0.45), "redness": (0.20, 0.45)},
        style_vec={"airy": (0.50, 0.80), "glow": (0.45, 0.80)},
    ),
}

# 人脸/形体目标统一放在 geometry 下；比例由指标模块按瞳距/身高归一化。
_GEOMETRY_OVERRIDES = {
    "natural": {
        "face_wh": (1.15, 1.50), "jaw": (0.65, 0.95), "eye_w": (0.38, 0.62),
        "waist_hip": (0.65, 0.98), "leg_body": (0.38, 0.68),
    },
    "tangshui": {
        "face_wh": (1.15, 1.30), "jaw": (0.64, 0.80), "eye_w": (0.48, 0.64),
        "waist_hip": (0.70, 0.86), "leg_body": (0.50, 0.64),
    },
    "cold_white": {
        "face_wh": (1.15, 1.42), "jaw": (0.68, 0.90), "eye_w": (0.40, 0.58),
    },
    "warm_film": {
        "face_wh": (1.15, 1.45), "jaw": (0.68, 0.92), "eye_w": (0.40, 0.60),
    },
    "night": {
        "face_wh": (1.15, 1.50), "jaw": (0.65, 0.95), "eye_w": (0.38, 0.62),
    },
    "id_photo": {
        "face_wh": (1.18, 1.42), "jaw": (0.70, 0.90), "eye_w": (0.40, 0.55),
    },
    "high_sat_low_contrast": {
        "face_wh": (1.13, 1.28), "jaw": (0.62, 0.78), "eye_w": (0.50, 0.66),
        "waist_hip": (0.68, 0.84), "leg_body": (0.50, 0.66),
    },
}
for _sid, _geometry in _GEOMETRY_OVERRIDES.items():
    if _sid in PROFILES:
        PROFILES[_sid] = replace(
            PROFILES[_sid],
            geometry={**PROFILES[_sid].geometry, **_geometry},
        )

_FINISH_OVERRIDES = {
    "tangshui": {"bokeh": (0.12, 0.30)},
    "high_sat_low_contrast": {"bokeh": (0.10, 0.28)},
}
for _sid, _finish in _FINISH_OVERRIDES.items():
    if _sid in PROFILES:
        PROFILES[_sid] = replace(
            PROFILES[_sid],
            finish={**PROFILES[_sid].finish, **_finish},
        )

# 妆容目标：强度是主目标；色相只在需要统一唇色/发色时使用。
_MAKEUP_OVERRIDES = {
    "natural": {
        "lip_strength": (0.0, 0.12), "lip_hue": (0.96, 1.0),
        "hair_strength": (0.0, 0.05), "eye_strength": (0.02, 0.12),
        "sclera": (0.0, 0.15),
    },
    "tangshui": {
        "lip_strength": (0.22, 0.42), "lip_hue": (0.96, 1.0),
        "hair_strength": (0.04, 0.12), "eye_strength": (0.18, 0.35),
        "sclera": (0.10, 0.25),
    },
    "cold_white": {
        "lip_strength": (0.12, 0.30), "lip_hue": (0.95, 0.99),
        "hair_strength": (0.02, 0.08), "eye_strength": (0.08, 0.22),
        "sclera": (0.08, 0.22),
    },
    "warm_film": {
        "lip_strength": (0.16, 0.32), "lip_hue": (0.94, 0.99),
        "hair_strength": (0.04, 0.12), "eye_strength": (0.08, 0.20),
        "sclera": (0.05, 0.18),
    },
    "night": {
        "lip_strength": (0.12, 0.28), "lip_hue": (0.95, 1.0),
        "hair_strength": (0.02, 0.08), "eye_strength": (0.12, 0.28),
        "sclera": (0.05, 0.18),
    },
    "id_photo": {
        "lip_strength": (0.04, 0.16), "lip_hue": (0.97, 1.0),
        "hair_strength": (0.0, 0.04), "eye_strength": (0.02, 0.12),
        "sclera": (0.02, 0.12),
    },
    "high_sat_low_contrast": {
        "lip_strength": (0.30, 0.50), "lip_hue": (0.95, 1.0),
        "hair_strength": (0.08, 0.18), "eye_strength": (0.22, 0.40),
        "sclera": (0.12, 0.28),
    },
}
for _sid, _makeup in _MAKEUP_OVERRIDES.items():
    if _sid in PROFILES:
        PROFILES[_sid] = replace(PROFILES[_sid], makeup=_makeup)

ALIASES = {
    "自然": "natural",
    "糖水": "tangshui",
    "通透": "tangshui",
    "冷白": "cold_white",
    "胶片": "warm_film",
    "暖调": "warm_film",
    "夜景": "night",
    "证件照": "id_photo",
    "高饱和": "high_sat_low_contrast",
    "网感": "high_sat_low_contrast",
    "网红": "high_sat_low_contrast",
}


def resolve_style(value: str | None, fallback: str = "natural") -> StyleProfile:
    if not value:
        return PROFILES.get(fallback, PROFILES["natural"])
    key = value.strip().lower()
    if key in PROFILES:
        return PROFILES[key]
    key = ALIASES.get(value.strip(), key)
    return PROFILES.get(key, PROFILES.get(fallback, PROFILES["natural"]))


def get_path(state: dict[str, Any], path: str) -> float | None:
    node: Any = state
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if isinstance(node, (int, float)):
        return float(node)
    return None


def style_distance(state: dict[str, Any], profile: StyleProfile) -> tuple[float, dict[str, float]]:
    """返回加权距离与每个目标的差值（正=高于目标，负=低于目标）。"""
    total = 0.0
    weight_sum = 0.0
    deltas: dict[str, float] = {}
    for path, (lo, hi) in profile.all_targets().items():
        value = get_path(state, path)
        if value is None:
            continue
        weight = float(profile.weights.get(path, 1.0))
        span = max(1e-6, hi - lo)
        if value < lo:
            delta = value - lo
        elif value > hi:
            delta = value - hi
        else:
            delta = 0.0
        deltas[path] = round(delta, 4)
        total += weight * abs(delta) / span
        weight_sum += weight
    return (total / weight_sum if weight_sum else 0.0), deltas


def style_target_text(profile: StyleProfile) -> str:
    lines = [f"{profile.id} / {profile.name}: {profile.description}"]
    for path, (lo, hi) in profile.all_targets().items():
        lines.append(f"  {path}: {lo} ~ {hi}")
    return "\n".join(lines)


def infer_style(state: dict[str, Any], project_theme: str = "") -> StyleProfile:
    """没有指定风格时，根据场景/色温/肤色/对比选最接近的预设。"""
    text = project_theme or ""
    for alias, style_id in ALIASES.items():
        if alias in text:
            return PROFILES[style_id]
    scene = str(state.get("image", {}).get("scene", ""))
    candidates: Iterable[str]
    if scene == "night":
        candidates = ("night", "warm_film", "natural")
    elif scene == "indoor_warm":
        candidates = ("tangshui", "warm_film", "natural")
    elif scene == "outdoor_cool":
        candidates = ("cold_white", "natural", "tangshui")
    else:
        candidates = ("natural", "tangshui", "cold_white")
    best = PROFILES["natural"]
    best_score = float("inf")
    for style_id in candidates:
        profile = PROFILES[style_id]
        score, _ = style_distance(state, profile)
        if score < best_score:
            best, best_score = profile, score
    return best
