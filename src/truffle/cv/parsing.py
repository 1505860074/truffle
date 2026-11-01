"""人脸解析 / 头发蒙版。

优先使用本地 ONNX 人脸解析模型（models/face_parsing.onnx）；
模型不存在时，用关键点 + 颜色相似度做可用的启发式回退。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .analyzer import Analysis


class FaceParser:
    def __init__(self, model_path: str | Path | None = None) -> None:
        self.session = None
        self.input_name = ""
        self.path = Path(model_path) if model_path else Path("models") / "face_parsing.onnx"
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            import onnxruntime as ort

            providers = []
            available = set(ort.get_available_providers())
            for name in ("CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"):
                if name in available:
                    providers.append(name)
            self.session = ort.InferenceSession(str(self.path), providers=providers or None)
            self.input_name = self.session.get_inputs()[0].name
        except Exception:
            self.session = None

    @property
    def available(self) -> bool:
        return self.session is not None

    def hair_mask(self, image: np.ndarray, analysis: Analysis | None = None) -> np.ndarray:
        if self.session is not None:
            parsed = self._infer(image)
            if parsed is not None:
                # CelebAMask-HQ / BiSeNet 常用类别 17 = hair
                mask = (parsed == 17).astype(np.uint8) * 255
                if mask.any():
                    return cv2.GaussianBlur(mask, (0, 0), 3)
        return _heuristic_hair(image, analysis)


def _infer(self: FaceParser, image: np.ndarray) -> np.ndarray | None:
    try:
        h, w = image.shape[:2]
        size = 512
        resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        rgb = (rgb - mean) / std
        blob = np.transpose(rgb, (2, 0, 1))[None].astype(np.float32)
        output = self.session.run(None, {self.input_name: blob})[0]
        parsed = np.argmax(output[0], axis=0).astype(np.uint8)
        return cv2.resize(parsed, (w, h), interpolation=cv2.INTER_NEAREST)
    except Exception:
        return None


FaceParser._infer = _infer  # type: ignore[attr-defined]


def _heuristic_hair(image: np.ndarray, analysis: Analysis | None) -> np.ndarray:
    h, w = image.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    if analysis is None or not analysis.faces:
        top = int(h * 0.35)
        hsv = cv2.cvtColor(image[:top], cv2.COLOR_BGR2HSV)
        dark = ((hsv[..., 2] < 120) | (hsv[..., 1] < 45)).astype(np.uint8) * 255
        mask[:top] = dark
        return cv2.GaussianBlur(mask, (0, 0), 5)

    for face in analysis.faces:
        if face.landmarks is None:
            continue
        x, y, bw, bh = face.box
        top = max(0, int(y - bh * 0.45))
        bottom = int(y + bh * 0.45)
        left = max(0, int(x - bw * 0.12))
        right = min(w, int(x + bw * 1.12))
        if right <= left or bottom <= top:
            continue
        roi = image[top:bottom, left:right]
        if roi.size == 0:
            continue
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # 头发通常：暗、低饱和，或与顶部条带颜色接近
        strip = image[top:max(top + 4, top + int(bh * 0.08)), left:right]
        if strip.size:
            strip_lab = cv2.cvtColor(strip, cv2.COLOR_BGR2LAB)
            target = np.median(strip_lab.reshape(-1, 3), axis=0)
            lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.float32)
            dist = np.linalg.norm(lab - target, axis=2)
            similar = (dist < 42).astype(np.uint8) * 255
        else:
            similar = np.zeros(roi.shape[:2], dtype=np.uint8)
        dark = ((hsv[..., 2] < 125) & (hsv[..., 1] < 90)).astype(np.uint8) * 255
        local = cv2.bitwise_or(similar, dark)
        local = cv2.morphologyEx(local, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        local = cv2.morphologyEx(local, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask[top:bottom, left:right] = cv2.bitwise_or(mask[top:bottom, left:right], local)
    return cv2.GaussianBlur(mask, (0, 0), 5)
