"""参数求解器：把「风格目标」变成工具参数。

LLM 只选风格和目标；这里用规则初值 + 坐标下降在预览图上搜索参数。
所有搜索都在本地完成，不经过大模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from ..cv.analyzer import Analyzer
from ..cv.metrics import measure
from ..tools.pipeline import render_pipeline
from ..tools.registry import ToolRegistry
from .style import StyleProfile, style_distance


@dataclass
class SolveResult:
    jobs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    evaluations: int = 0
    naturalness: float = 1.0
    notes: list[str] = field(default_factory=list)


def _clip(value: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, value)))


def _center(profile: StyleProfile, key: str, fallback: float | None = None) -> float | None:
    bounds = profile.all_targets().get(key)
    if bounds is None:
        return fallback
    return (bounds[0] + bounds[1]) / 2.0


def _upper(profile: StyleProfile, key: str, fallback: float | None = None) -> float | None:
    bounds = profile.all_targets().get(key)
    if bounds is None:
        return fallback
    return bounds[1]


def _lower(profile: StyleProfile, key: str, fallback: float | None = None) -> float | None:
    bounds = profile.all_targets().get(key)
    if bounds is None:
        return fallback
    return bounds[0]


def _median_face_skin(state: dict[str, Any], key: str) -> float | None:
    values = [
        item.get("skin", {}).get(key)
        for item in state.get("faces", [])
        if isinstance(item, dict) and item.get("skin", {}).get(key) is not None
    ]
    return float(np.median(values)) if values else None


def _median_face_ratio(state: dict[str, Any], key: str) -> float | None:
    values = [
        item.get("ratio", {}).get(key)
        for item in state.get("faces", [])
        if isinstance(item, dict) and item.get("ratio", {}).get(key) is not None
    ]
    return float(np.median(values)) if values else None


class ParamSolver:
    def __init__(
        self,
        registry: ToolRegistry,
        analyzer: Analyzer,
        *,
        preview_max: int = 640,
        max_iterations: int = 2,
        max_evaluations: int = 18,
    ) -> None:
        self.registry = registry
        self.analyzer = analyzer
        self.preview_max = preview_max
        self.max_iterations = max_iterations
        self.max_evaluations = max_evaluations

    # ---------- 对外 ----------
    def solve(
        self,
        image: np.ndarray,
        profile: StyleProfile,
        state: dict[str, Any] | None = None,
        allowed: set[str] | None = None,
    ) -> SolveResult:
        preview = _downscale(image, self.preview_max)
        before = state or measure(preview, self.analyzer)
        jobs = self._initial_jobs(before, profile, allowed)
        best_jobs = list(jobs)
        best_score = self._score(preview, best_jobs, profile)
        evaluations = 1
        if not best_jobs:
            return SolveResult(
                jobs=[],
                before=before,
                after=before,
                score=best_score,
                evaluations=evaluations,
                notes=["没有可调参数"],
            )

        step = 0.08
        for _ in range(self.max_iterations):
            improved = False
            for index in range(len(best_jobs)):
                tool_name, params = best_jobs[index]
                for key in list(params.keys()):
                    if not isinstance(params[key], (int, float)) or isinstance(params[key], bool):
                        continue
                    current = float(params[key])
                    for candidate in (current - step, current + step):
                        if evaluations >= self.max_evaluations:
                            break
                        trial = [item for item in best_jobs]
                        new_params = dict(params)
                        new_params[key] = candidate
                        trial[index] = (tool_name, new_params)
                        score = self._score(preview, trial, profile)
                        evaluations += 1
                        if score + 1e-4 < best_score:
                            best_score = score
                            best_jobs = trial
                            params = new_params
                            improved = True
                    if evaluations >= self.max_evaluations:
                        break
                if evaluations >= self.max_evaluations:
                    break
            if not improved or evaluations >= self.max_evaluations:
                break

        best_jobs = self._clean(best_jobs)
        after = render_pipeline(self.registry, self.analyzer, preview, best_jobs) if best_jobs else preview
        after_state = measure(after, self.analyzer, body=False)
        naturalness = self._naturalness(best_jobs, after_state)
        notes = []
        distance, _ = style_distance(after_state, profile)
        if distance > 0.25:
            notes.append("风格目标仍有偏差")
        if naturalness < 0.65:
            notes.append("当前参数偏强，可能不自然")
        return SolveResult(
            jobs=best_jobs,
            before=before,
            after=after_state,
            score=best_score,
            evaluations=evaluations,
            naturalness=naturalness,
            notes=notes,
        )

    # ---------- 初值 ----------
    def _initial_jobs(
        self,
        state: dict[str, Any],
        profile: StyleProfile,
        allowed: set[str] | None,
    ) -> list[tuple[str, dict[str, Any]]]:
        jobs: list[tuple[str, dict[str, Any]]] = []

        def allow(name: str) -> bool:
            return allowed is None or name in allowed

        tone = state.get("tone", {})
        color = state.get("color", {})
        quality = state.get("quality", {})

        ev = _center(profile, "tone.ev")
        contrast = _center(profile, "tone.contrast")
        sat = _center(profile, "color.sat")
        brightness = _clip((ev - float(tone.get("ev", 0.0))) / 2.0, -0.6, 0.6) if ev is not None else 0.0
        contrast_value = _clip(contrast - float(tone.get("contrast", 0.0)), -0.6, 0.6) if contrast is not None else 0.0
        sat_value = _clip(sat - float(color.get("sat", 0.0)), -0.5, 0.6) if sat is not None else 0.0
        if allow("color_adjust") and any(abs(v) > 0.02 for v in (brightness, contrast_value, sat_value)):
            jobs.append(("color_adjust", {
                "brightness": round(brightness, 3),
                "contrast": round(contrast_value, 3),
                "saturation": round(sat_value, 3),
            }))

        wb_target = _center(profile, "tone.wb_k")
        if allow("color_temp") and wb_target is not None:
            temperature = _clip((wb_target - float(tone.get("wb_k", wb_target))) / 4000.0, -0.6, 0.6)
            tint = 0.0
            skin_a_target = _center(profile, "color.skin_a")
            if skin_a_target is not None:
                tint = _clip((skin_a_target - float(color.get("skin_a", 0.0))) / 40.0, -0.4, 0.4)
            if abs(temperature) > 0.02 or abs(tint) > 0.02:
                jobs.append(("color_temp", {
                    "temperature": round(temperature, 3),
                    "tint": round(tint, 3),
                }))

        shadow_target = _center(profile, "tone.shadow")
        highlight_max = _upper(profile, "tone.clip_hi")
        highlights = 0.0
        shadows = 0.0
        if highlight_max is not None and float(tone.get("clip_hi", 0.0)) > highlight_max:
            highlights = -_clip(
                (float(tone.get("clip_hi", 0.0)) - highlight_max) / max(0.01, highlight_max + 0.005),
                0.0,
                0.5,
            )
        if shadow_target is not None:
            shadows = _clip(shadow_target - float(tone.get("shadow", 0.0)), -0.35, 0.5)
        if allow("tone_recovery") and (abs(highlights) > 0.02 or abs(shadows) > 0.02):
            jobs.append(("tone_recovery", {
                "highlights": round(highlights, 3),
                "shadows": round(shadows, 3),
            }))

        texture = _median_face_skin(state, "texture")
        texture_max = _upper(profile, "skin.texture")
        if allow("skin_smooth") and texture is not None and texture_max is not None:
            strength = _clip((texture - texture_max) / 0.55, 0.0, 0.75)
            if strength > 0.05:
                jobs.append(("skin_smooth", {"strength": round(strength, 3)}))

        skin_l = _center(profile, "color.skin_L")
        if allow("whiten") and skin_l is not None:
            strength = _clip((skin_l - float(color.get("skin_L", skin_l))) / 0.35, 0.0, 0.6)
            if strength > 0.05:
                jobs.append(("whiten", {"strength": round(strength, 3)}))

        blemish = _median_face_skin(state, "blemish")
        if allow("remove_blemish") and blemish is not None and blemish > 1:
            jobs.append(("remove_blemish", {
                "strength": round(_clip(0.25 + blemish * 0.05, 0.2, 0.65), 3),
                "threshold": 12.0,
            }))

        under_eye = _median_face_skin(state, "under_eye")
        under_max = _upper(profile, "skin.under_eye")
        if allow("remove_dark_circles") and under_eye is not None and under_max is not None:
            strength = _clip((under_eye - under_max) / 0.3, 0.0, 0.6)
            if strength > 0.05:
                jobs.append(("remove_dark_circles", {"strength": round(strength, 3)}))

        teeth = _median_face_skin(state, "teeth_yellow")
        if allow("teeth_whiten") and teeth is not None and teeth > 0.25:
            jobs.append(("teeth_whiten", {"strength": round(_clip((teeth - 0.2) / 0.5, 0.2, 0.6), 3)}))

        lip_strength = _center(profile, "makeup.lip_strength")
        if allow("lipstick") and state.get("faces") and lip_strength is not None and lip_strength > 0.05:
            jobs.append(("lipstick", {
                "hue": round(float(_center(profile, "makeup.lip_hue", 0.98)), 3),
                "strength": round(_clip(lip_strength, 0.05, 0.55), 3),
            }))

        hair_strength = _center(profile, "makeup.hair_strength")
        if allow("hair_color") and state.get("faces") and hair_strength is not None and hair_strength > 0.03:
            jobs.append(("hair_color", {
                "hue": round(float(_center(profile, "makeup.hair_hue", 0.05)), 3),
                "strength": round(_clip(hair_strength, 0.03, 0.25), 3),
            }))

        eye_strength = _center(profile, "makeup.eye_strength")
        if allow("eye_brighten") and state.get("faces") and eye_strength is not None and eye_strength > 0.04:
            jobs.append(("eye_brighten", {
                "strength": round(_clip(eye_strength, 0.04, 0.45), 3),
                "sclera": round(_clip(float(_center(profile, "makeup.sclera", 0.2)), 0.0, 0.5), 3),
            }))

        glow_target = _center(profile, "style_vec.glow")
        if allow("face_light") and state.get("faces") and glow_target is not None:
            current_glow = float(state.get("style_vec", {}).get("glow", glow_target))
            strength = _clip((glow_target - current_glow) * 0.9, 0.0, 0.35)
            if strength > 0.03:
                jobs.append(("face_light", {
                    "strength": round(strength, 3),
                    "warmth": 0.0,
                    "feather": 0.5,
                }))

        noise_value = float(quality.get("noise", 0.0))
        noise_max = _upper(profile, "quality.noise")
        if allow("noise_reduction") and noise_max is not None and noise_value > noise_max:
            noise_strength = _clip((noise_value - noise_max) / 0.25, 0.0, 0.6)
            if noise_strength > 0.03:
                jobs.append(("noise_reduction", {
                    "strength": round(noise_strength, 3),
                    "color": round(_clip(noise_strength * 0.8, 0.0, 0.6), 3),
                }))

        sharp_target = _center(profile, "quality.sharp")
        if allow("sharpen_clarity") and sharp_target is not None:
            sharpen = _clip((sharp_target - float(quality.get("sharp", sharp_target))) / 0.5, 0.0, 0.55)
            clarity = _clip((sharp_target - float(quality.get("sharp", sharp_target))) / 1.2, -0.3, 0.25)
            if sharpen > 0.02 or abs(clarity) > 0.02:
                jobs.append(("sharpen_clarity", {
                    "sharpen": round(sharpen, 3),
                    "clarity": round(clarity, 3),
                }))

        face_wh = _median_face_ratio(state, "face_wh")
        face_wh_max = _upper(profile, "geometry.face_wh")
        jaw = _median_face_ratio(state, "jaw")
        jaw_max = _upper(profile, "geometry.jaw")
        if allow("slim_face") and face_wh is not None and face_wh_max is not None:
            strength = _clip((face_wh - face_wh_max) * 2.5, 0.0, 0.6)
            if jaw is not None and jaw_max is not None:
                strength = max(strength, _clip((jaw - jaw_max) * 2.0, 0.0, 0.6))
            if strength > 0.03:
                jobs.append(("slim_face", {"strength": round(strength, 3)}))

        eye_ratio = _median_face_ratio(state, "eye_w")
        eye_min = _lower(profile, "geometry.eye_w")
        if allow("enlarge_eyes") and eye_ratio is not None and eye_min is not None:
            strength = _clip((eye_min - eye_ratio) * 2.0, 0.0, 0.45)
            if strength > 0.03:
                jobs.append(("enlarge_eyes", {"strength": round(strength, 3)}))

        body = state.get("body") or {}
        waist = body.get("waist_hip")
        waist_max = _upper(profile, "geometry.waist_hip")
        if allow("body_slim") and waist is not None and waist_max is not None:
            strength = _clip((float(waist) - waist_max) * 2.5, 0.0, 0.5)
            if strength > 0.03:
                jobs.append(("body_slim", {"strength": round(strength, 3)}))

        leg = body.get("leg_body")
        leg_min = _lower(profile, "geometry.leg_body")
        if allow("leg_lengthen") and leg is not None and leg_min is not None:
            strength = _clip((leg_min - float(leg)) * 2.0, 0.0, 0.45)
            if strength > 0.03:
                jobs.append(("leg_lengthen", {"strength": round(strength, 3)}))

        bokeh = _center(profile, "finish.bokeh")
        if allow("background_blur") and bokeh is not None and bokeh > 0.05 and state.get("faces"):
            jobs.append(("background_blur", {
                "strength": round(_clip(bokeh, 0.05, 0.45), 3),
                "feather": 0.45,
            }))

        grain = _center(profile, "finish.grain")
        if allow("film") and grain is not None and grain > 0.02:
            jobs.append(("film", {
                "grain": round(_clip(grain * 1.8, 0.05, 0.5), 3),
                "fade": round(_clip(grain * 1.2, 0.02, 0.25), 3),
            }))

        vignette = _center(profile, "finish.vignette")
        if allow("vignette") and vignette is not None and vignette > 0.02:
            jobs.append(("vignette", {
                "amount": round(_clip(vignette, 0.05, 0.4), 3),
                "softness": 0.6,
            }))

        return jobs

    # ---------- 评分 ----------
    def _score(
        self,
        preview: np.ndarray,
        jobs: list[tuple[str, dict[str, Any]]],
        profile: StyleProfile,
    ) -> float:
        if not jobs:
            state = measure(preview, self.analyzer, body=False)
        else:
            rendered = render_pipeline(self.registry, self.analyzer, preview, jobs)
            state = measure(rendered, self.analyzer, body=False)
        distance, _ = style_distance(state, profile)
        return float(distance + self._naturalness_penalty(jobs, state))

    def _naturalness_penalty(
        self, jobs: list[tuple[str, dict[str, Any]]], state: dict[str, Any]
    ) -> float:
        penalty = 0.0
        for name, params in jobs:
            strength = float(params.get("strength", 0.0) or 0.0)
            if name == "skin_smooth" and strength > 0.65:
                penalty += (strength - 0.65) * 1.8
            elif name in ("slim_face", "enlarge_eyes", "body_slim", "leg_lengthen") and strength > 0.55:
                penalty += (strength - 0.55) * 1.6
            elif name == "color_adjust":
                penalty += max(0.0, abs(float(params.get("saturation", 0.0))) - 0.5) * 0.8
        quality = state.get("quality", {})
        penalty += float(quality.get("clip_hi", 0.0)) * 4.0
        penalty += float(quality.get("noise", 0.0)) * 0.4
        return penalty

    def _naturalness(self, jobs: list[tuple[str, dict[str, Any]]], state: dict[str, Any]) -> float:
        return _clip(1.0 - self._naturalness_penalty(jobs, state), 0.0, 1.0)

    @staticmethod
    def _clean(jobs: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
        out: list[tuple[str, dict[str, Any]]] = []
        for name, params in jobs:
            cleaned = {
                key: value
                for key, value in params.items()
                if not (isinstance(value, (int, float)) and not isinstance(value, bool) and abs(float(value)) < 0.005)
            }
            if cleaned:
                out.append((name, cleaned))
        return out


def _downscale(image: np.ndarray, max_side: int) -> np.ndarray:
    h, w = image.shape[:2]
    if max(h, w) <= max_side:
        return image
    scale = max_side / float(max(h, w))
    return cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
