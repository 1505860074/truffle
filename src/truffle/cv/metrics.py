"""图像量化指标：把「现在画面是什么样」编码成可比较的文字/JSON。

这些指标是 AI Agent 的眼睛：LLM 看不到原图，只读取这里的数值。
所有指标尽量归一化到 0~1，或使用明确单位（EV、K、百分比）。
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from .analyzer import (
    EYE_LEFT,
    EYE_RIGHT,
    FACE_OVAL,
    JAW_LEFT,
    JAW_RIGHT,
    MOUTH_INNER,
    NOSE,
    POSE_L_ANKLE,
    POSE_L_HIP,
    POSE_L_SHOULDER,
    POSE_R_ANKLE,
    POSE_R_HIP,
    POSE_R_SHOULDER,
    Analysis,
    Analyzer,
    Face,
)

STATE_SCHEMA = "state.v1"


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, value)))


def _mean(values: np.ndarray | list[float]) -> float:
    arr = np.asarray(values, dtype=np.float32)
    return float(arr.mean()) if arr.size else 0.0


def _pt(points: np.ndarray, index: int) -> np.ndarray:
    return np.asarray(points[index], dtype=np.float32)


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float32) - np.asarray(b, dtype=np.float32)))


def _center(points: np.ndarray, indices: list[int]) -> np.ndarray:
    return np.mean([_pt(points, i) for i in indices], axis=0)


def _bbox(points: np.ndarray, indices: list[int]) -> tuple[float, float, float, float]:
    pts = np.array([_pt(points, i) for i in indices], dtype=np.float32)
    x0, y0 = pts[:, 0].min(), pts[:, 1].min()
    x1, y1 = pts[:, 0].max(), pts[:, 1].max()
    return float(x0), float(y0), float(x1), float(y1)


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _global_metrics(image: np.ndarray, analysis: Analysis | None) -> dict[str, Any]:
    gray = _gray(image).astype(np.float32)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)

    mean_luma = float(gray.mean())
    ev = float(math.log2(max(mean_luma, 1.0) / 127.5))
    contrast = _clip(float(gray.std()) / 96.0, 0.0, 2.0)
    sat = _clip(float(hsv[..., 1].mean()) / 255.0)
    val = hsv[..., 2]
    vib = _clip(float(np.mean(val < 160) * (1.0 - sat * 0.5)), 0.0, 1.0)

    b, g, r = (image[..., i].astype(np.float32) for i in range(3))
    rg = r - g
    yb = 0.5 * (r + g) - b
    colorfulness = float(
        math.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * math.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    )
    colorfulness = _clip(colorfulness / 120.0)

    clip_hi = _clip(float(np.mean((image >= 250).any(axis=2))))
    clip_lo = _clip(float(np.mean((image <= 5).any(axis=2))))

    hist = np.histogram(gray, bins=3, range=(0, 255))[0].astype(np.float32)
    hist = hist / max(1.0, hist.sum())
    shadow, mid, high = (float(v) for v in hist)

    b_mean, g_mean, r_mean = float(b.mean()), float(g.mean()), float(r.mean())
    warmth = (r_mean - b_mean) / max(1.0, r_mean + b_mean)
    tint = (g_mean - (r_mean + b_mean) / 2.0) / max(1.0, g_mean + (r_mean + b_mean) / 2.0)
    # 场景色温的近似值：偏暖更高 K，偏冷更低 K（仅用于描述，不是严格白平衡）
    wb_k = 6500.0 * float(np.clip(1.0 + warmth * 1.8, 0.6, 1.6))

    skin_hue = skin_sat = skin_l = skin_a = 0.0
    if analysis is not None and analysis.skin_mask is not None:
        mask = analysis.skin_mask > 32
        if mask.any():
            skin_hue = float(np.median(hsv[..., 0][mask])) * 2.0  # OpenCV H: 0~179 -> 0~358
            skin_sat = _clip(float(np.median(hsv[..., 1][mask])) / 255.0)
            skin_l = _clip(float(np.median(lab[..., 0][mask])) / 255.0)
            skin_a = float(np.median(lab[..., 1][mask]) - 128.0)

    laplacian = cv2.Laplacian(gray, cv2.CV_32F)
    sharp = _clip(float(laplacian.var()) / 900.0, 0.0, 2.0)
    noise = _noise_estimate(gray)
    haze = _haze_estimate(image, contrast)

    airy = _clip(0.45 * high + 0.25 * shadow + 0.30 * (1.0 - min(contrast, 1.0)))
    glow = _clip(0.6 * high + 0.4 * (1.0 - min(contrast, 1.0)))
    cool_shadow = 0.0
    shadow_mask = gray < 90
    if shadow_mask.any():
        sb = float(b[shadow_mask].mean())
        sr = float(r[shadow_mask].mean())
        cool_shadow = _clip((sb - sr) / max(1.0, sb + sr) * 2.0 + 0.5)
    film = _clip(0.45 * (1.0 - sat) + 0.3 * noise + 0.25 * (1.0 - min(contrast, 1.0)))

    return {
        "tone": {
            "ev": round(ev, 3),
            "contrast": round(contrast, 3),
            "wb_k": round(wb_k, 1),
            "tint": round(tint, 4),
            "clip_hi": round(clip_hi, 4),
            "clip_lo": round(clip_lo, 4),
            "shadow": round(shadow, 3),
            "mid": round(mid, 3),
            "high": round(high, 3),
        },
        "color": {
            "sat": round(sat, 3),
            "vib": round(vib, 3),
            "colorfulness": round(colorfulness, 3),
            "skin_hue": round(skin_hue, 1),
            "skin_sat": round(skin_sat, 3),
            "skin_L": round(skin_l, 3),
            "skin_a": round(skin_a, 1),
        },
        "quality": {
            "sharp": round(sharp, 3),
            "noise": round(noise, 3),
            "haze": round(haze, 3),
            "artifact": round(clip_hi * 0.5 + clip_lo * 0.3, 3),
            "oversmooth": 0.0,
            "warp_smooth": 0.0,
        },
        "style_vec": {
            "warmth": round(_clip((warmth + 0.2) / 0.4), 3),
            "airy": round(airy, 3),
            "contrast": round(_clip(contrast), 3),
            "glow": round(glow, 3),
            "cool_shadow": round(cool_shadow, 3),
            "film": round(film, 3),
        },
    }


def _noise_estimate(gray: np.ndarray) -> float:
    """平坦区高频残差，近似估计噪点。"""
    if gray.size < 64:
        return 0.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.abs(gx) + np.abs(gy)
    flat = grad < np.percentile(grad, 35)
    if not flat.any():
        return 0.0
    residual = gray - cv2.GaussianBlur(gray, (0, 0), 1.2)
    return _clip(float(np.std(residual[flat])) / 24.0)


def _haze_estimate(image: np.ndarray, contrast: float) -> float:
    b, g, r = (image[..., i].astype(np.float32) for i in range(3))
    dark = np.minimum(np.minimum(b, g), r)
    dark_channel = cv2.erode(dark, np.ones((7, 7), np.uint8))
    airlight = float(np.percentile(dark_channel, 90))
    return _clip((airlight / 255.0) * 0.7 + (1.0 - min(contrast, 1.0)) * 0.3)


def _face_metrics(
    face: Face, image: np.ndarray, skin_mask: np.ndarray | None, index: int
) -> dict[str, Any] | None:
    lm = face.landmarks
    if lm is None:
        return None
    h, w = image.shape[:2]
    ipd = max(1.0, _dist(_center(lm, EYE_LEFT), _center(lm, EYE_RIGHT)))
    face_box = _bbox(lm, FACE_OVAL)
    face_w = max(1.0, face_box[2] - face_box[0])
    face_h = max(1.0, face_box[3] - face_box[1])
    jaw = _bbox(lm, JAW_LEFT)[0], _bbox(lm, JAW_RIGHT)[2]
    jaw_w = max(1.0, jaw[1] - jaw[0])
    cheek_w = max(1.0, _dist(_pt(lm, 234), _pt(lm, 454)))
    chin_len = max(1.0, _pt(lm, 152)[1] - _pt(lm, 2)[1])
    eye_l = _bbox(lm, EYE_LEFT)
    eye_w = max(1.0, eye_l[2] - eye_l[0])
    eye_h = max(1.0, eye_l[3] - eye_l[1])
    nose_w = max(1.0, _dist(_pt(lm, NOSE[2]), _pt(lm, NOSE[3])))
    mouth_w = max(1.0, _dist(_pt(lm, 61), _pt(lm, 291)))
    symmetry = _symmetry(lm)

    top = _pt(lm, 10)[1]
    brow = float(np.mean([_pt(lm, 8)[1], _pt(lm, 9)[1]]))
    nose_y = _pt(lm, 2)[1]
    chin = _pt(lm, 152)[1]
    total = max(1.0, chin - top)
    third_upper = _clip((brow - top) / total)
    third_mid = _clip((nose_y - brow) / total)
    third_low = _clip((chin - nose_y) / total)

    skin = _skin_face_metrics(image, face, skin_mask)
    return {
        "id": f"f{index + 1}",
        "box": [int(v) for v in face.box],
        "ratio": {
            "face_wh": round(face_w / face_h, 3),
            "jaw": round(jaw_w / ipd, 3),
            "cheek": round(cheek_w / ipd, 3),
            "chin": round(chin_len / face_h, 3),
            "eye_w": round(eye_w / ipd, 3),
            "eye_ar": round(eye_h / eye_w, 3),
            "nose_w": round(nose_w / ipd, 3),
            "mouth_w": round(mouth_w / ipd, 3),
            "symmetry": round(symmetry, 3),
            "third_upper": round(third_upper, 3),
            "third_mid": round(third_mid, 3),
            "third_low": round(third_low, 3),
        },
        "skin": skin,
    }


def _symmetry(points: np.ndarray) -> float:
    pairs = [(33, 263), (61, 291), (234, 454), (127, 356), (70, 300), (172, 397)]
    if not pairs:
        return 1.0
    vals = []
    for left, right in pairs:
        p1, p2 = _pt(points, left), _pt(points, right)
        mid = (p1 + p2) / 2.0
        vals.append(abs(p1[0] - mid[0]) + abs(p2[0] - mid[0]))
    scale = max(1.0, _dist(_pt(points, 234), _pt(points, 454)))
    return _clip(1.0 - float(np.mean(vals)) / scale * 2.0)


def _skin_face_metrics(
    image: np.ndarray, face: Face, skin_mask: np.ndarray | None
) -> dict[str, Any]:
    x, y, w, h = face.box
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(image.shape[1], x + w), min(image.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return _empty_skin()
    roi = image[y0:y1, x0:x1]
    if skin_mask is not None:
        mask = skin_mask[y0:y1, x0:x1] > 32
    else:
        mask = np.ones(roi.shape[:2], dtype=bool)
    if not mask.any():
        return _empty_skin()

    gray = _gray(roi).astype(np.float32)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    residual = gray - cv2.GaussianBlur(gray, (0, 0), 2.0)
    texture = _clip(float(np.std(residual[mask])) / 24.0)
    redness = _clip((float(np.mean(lab[..., 1][mask])) - 128.0 + 32.0) / 64.0)
    specular = _clip(float(np.mean(hsv[..., 2][mask] > 240)))
    l_vals = lab[..., 0][mask].astype(np.float32)
    evenness = _clip(1.0 - float(np.std(l_vals)) / 64.0)

    # 痘斑：残差里明显高于局部中位数的连通块数量
    blemish = 0
    try:
        spots = (residual > 10.0).astype(np.uint8)
        spots = cv2.morphologyEx(spots, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(spots, 8)
        blemish = int(sum(1 for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 3))
    except Exception:  # noqa: BLE001
        blemish = 0

    under_eye = _under_eye_darkness(roi, face, x0, y0)
    teeth_yellow = _teeth_yellow(roi, face, x0, y0)
    return {
        "texture": round(texture, 3),
        "redness": round(redness, 3),
        "specular": round(specular, 3),
        "blemish": int(blemish),
        "under_eye": round(under_eye, 3),
        "evenness": round(evenness, 3),
        "teeth_yellow": round(teeth_yellow, 3),
    }


def _empty_skin() -> dict[str, Any]:
    return {
        "texture": 0.0,
        "redness": 0.0,
        "specular": 0.0,
        "blemish": 0,
        "under_eye": 0.0,
        "evenness": 1.0,
        "teeth_yellow": 0.0,
    }


def _under_eye_darkness(roi: np.ndarray, face: Face, ox: int, oy: int) -> float:
    lm = face.landmarks
    if lm is None:
        return 0.0
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    try:
        left = _pt(lm, 133)
        right = _pt(lm, 362)
        y = int((left[1] + right[1]) / 2 - oy)
        x0 = int(min(left[0], right[0]) - ox)
        x1 = int(max(left[0], right[0]) - ox)
        if y < 0 or y + 8 >= lab.shape[0] or x1 <= x0:
            return 0.0
        under = lab[max(0, y + 3):min(lab.shape[0], y + 10), max(0, x0):min(lab.shape[1], x1)]
        cheek = lab[max(0, y - 14):max(1, y - 5), max(0, x0):min(lab.shape[1], x1)]
        if under.size == 0 or cheek.size == 0:
            return 0.0
        return _clip((float(cheek.mean()) - float(under.mean())) / 64.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _teeth_yellow(roi: np.ndarray, face: Face, ox: int, oy: int) -> float:
    lm = face.landmarks
    if lm is None:
        return 0.0
    try:
        pts = np.array([_pt(lm, i) for i in MOUTH_INNER], dtype=np.float32)
        x0, x1 = int(pts[:, 0].min()) - ox, int(pts[:, 0].max()) - ox
        y0, y1 = int(pts[:, 1].min()) - oy, int(pts[:, 1].max()) - oy
        x0, x1 = max(0, x0), min(roi.shape[1], x1)
        y0, y1 = max(0, y0), min(roi.shape[0], y1)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        mouth = roi[y0:y1, x0:x1]
        lab = cv2.cvtColor(mouth, cv2.COLOR_BGR2LAB)
        b = float(np.median(lab[..., 2])) - 128.0
        return _clip((b + 12.0) / 40.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _body_metrics(pose: np.ndarray | None) -> dict[str, Any] | None:
    if pose is None or len(pose) < 29:
        return None
    try:
        ls, rs = _pt(pose, POSE_L_SHOULDER), _pt(pose, POSE_R_SHOULDER)
        lh, rh = _pt(pose, POSE_L_HIP), _pt(pose, POSE_R_HIP)
        la, ra = _pt(pose, POSE_L_ANKLE), _pt(pose, POSE_R_ANKLE)
        shoulder = _dist(ls, rs)
        hip = _dist(lh, rh)
        waist = _dist((ls + lh) / 2, (rs + rh) / 2)
        leg = (_dist(lh, la) + _dist(rh, ra)) / 2.0
        height = max(1.0, (_dist(_pt(pose, 0), (la + ra) / 2)))
        center = np.mean([ls, rs, lh, rh], axis=0)
        sym = 1.0 - (_dist(ls, center) + _dist(lh, center) - _dist(rs, center) - _dist(rh, center))
        return {
            "pose_conf": 1.0,
            "shoulder_hip": round(shoulder / max(1.0, hip), 3),
            "waist_hip": round(waist / max(1.0, hip), 3),
            "leg_body": round(leg / max(1.0, height), 3),
            "symmetry": round(_clip(sym), 3),
        }
    except Exception:  # noqa: BLE001
        return None


def measure(
    image: np.ndarray,
    analyzer: Analyzer | None = None,
    *,
    faces: bool = True,
    body: bool = True,
) -> dict[str, Any]:
    """返回 state.v1 结构化状态。"""
    analyzer = analyzer or Analyzer()
    analysis = analyzer.analyze(image) if faces else None
    result: dict[str, Any] = {
        "schema": STATE_SCHEMA,
        "image": {
            "w": int(image.shape[1]),
            "h": int(image.shape[0]),
            "scene": _scene_hint(image),
            "subject": "portrait" if analysis is not None and analysis.faces else "unknown",
        },
    }
    global_metrics = _global_metrics(image, analysis)
    result.update(global_metrics)
    if faces and analysis is not None:
        face_items = [
            item
            for i, face in enumerate(analysis.faces)
            if (item := _face_metrics(face, image, analysis.skin_mask, i)) is not None
        ]
        result["faces"] = face_items
    else:
        result["faces"] = []
    if body:
        pose = analyzer.pose(image)
        body_item = _body_metrics(pose)
        if body_item is not None:
            result["body"] = body_item
    return result


def _scene_hint(image: np.ndarray) -> str:
    """极简场景提示：后续可替换为本地 ONNX 场景分类器。"""
    gray = _gray(image).astype(np.float32)
    mean = float(gray.mean())
    b, g, r = (float(image[..., i].mean()) for i in range(3))
    warm = r > b + 12
    cool = b > r + 12
    if mean < 70:
        return "night"
    if mean > 190:
        return "bright"
    if warm:
        return "indoor_warm"
    if cool:
        return "outdoor_cool"
    return "natural"


def measure_text(image: np.ndarray, analyzer: Analyzer | None = None) -> str:
    """紧凑 JSON 文本，直接放进 prompt。"""
    import json

    return json.dumps(measure(image, analyzer), ensure_ascii=False, separators=(",", ":"))
