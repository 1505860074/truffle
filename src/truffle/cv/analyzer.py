"""图像分析：人脸框、人脸关键点、皮肤掩膜。

- 人脸关键点优先用 MediaPipe FaceMesh（468 点，含五官细节）；
- 若 MediaPipe 不可用，降级为 OpenCV Haar 级联，只给人脸框、无关键点；
- 皮肤掩膜用 YCrCb 颜色阈值，无额外模型依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

try:  # MediaPipe 为可选依赖，缺失时降级
    import mediapipe as mp

    _HAS_MEDIAPIPE = True
except Exception:  # pragma: no cover - 环境相关
    _HAS_MEDIAPIPE = False


# 脸型外轮廓（发色定位/遮挡判断用）
FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379,
    378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127,
    162, 21, 54, 103, 67, 109,
]
# 下颌 / 脸颊两侧（用于瘦脸：向脸中线挤压）
JAW_LEFT = [234, 93, 132, 58, 172, 136, 150, 149, 176, 148]
JAW_RIGHT = [454, 323, 361, 288, 397, 365, 379, 378, 400, 377]
# 眼睛轮廓（用于大眼 / 眼睛提亮）
EYE_LEFT = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
EYE_RIGHT = [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466]
# 眉毛（祛痘时保护，避免误伤）
EYEBROW_LEFT = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
EYEBROW_RIGHT = [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]
# 嘴：外唇 / 内唇（口红取「外唇−内唇」；牙齿美白取内唇）
MOUTH_OUTER = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
MOUTH_INNER = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]
# 鼻部（祛痘时保护）
NOSE = [1, 2, 98, 327, 168, 6, 197, 195]
# MediaPipe Pose 关键点索引（33 点拓扑）
POSE_L_SHOULDER, POSE_R_SHOULDER = 11, 12
POSE_L_HIP, POSE_R_HIP = 23, 24
POSE_L_KNEE, POSE_R_KNEE = 25, 26
POSE_L_ANKLE, POSE_R_ANKLE = 27, 28


@dataclass
class Face:
    box: tuple[int, int, int, int]  # x, y, w, h
    landmarks: np.ndarray | None = None  # (N, 2) float32，None 表示无关键点

    @property
    def center(self) -> tuple[float, float]:
        x, y, w, h = self.box
        return (x + w / 2.0, y + h / 2.0)


@dataclass
class Analysis:
    faces: list[Face] = field(default_factory=list)
    skin_mask: np.ndarray | None = None  # (H, W) uint8，255=皮肤


def _skin_mask(image: np.ndarray) -> np.ndarray:
    """基于 YCrCb 阈值的皮肤掩膜，含形态学去噪与羽化。"""
    ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=5)
    return mask


def refine_mask(image: np.ndarray, mask: np.ndarray, radius: int = 8, eps: float = 1e-3) -> np.ndarray:
    """用导向滤波把掩膜边缘贴合图像内容（边缘更干净），失败时原样返回。"""
    try:
        refined = cv2.ximgproc.guidedFilter(
            guide=image,
            src=mask.astype(np.float32),
            radius=radius,
            eps=eps * 255.0 * 255.0,
        )
        return np.clip(refined, 0, 255).astype(np.uint8)
    except Exception:  # pragma: no cover - 依赖可选模块
        return mask


class Analyzer:
    """图像分析器。实例可在多次调用间复用，内部按图像身份做缓存。"""

    def __init__(self, max_faces: int = 5) -> None:
        self.max_faces = max_faces
        self._cache: dict[tuple, Analysis] = {}
        self._mesh = None
        if _HAS_MEDIAPIPE:
            try:
                self._mesh = mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=True,
                    max_num_faces=max_faces,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                )
            except Exception:  # 模型缺失等：降级为 Haar
                self._mesh = None
        self._haar = None
        if self._mesh is None:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._haar = cv2.CascadeClassifier(cascade_path)
        # 姿态 / 人像分割按需惰性初始化（首次调用才加载模型）
        self._pose = None
        self._segmenter = None
        self._pose_cache: dict[tuple, np.ndarray | None] = {}
        self._seg_cache: dict[tuple, np.ndarray | None] = {}

    # ---------- 对外 ----------
    def analyze(self, image: np.ndarray) -> Analysis:
        key = (id(image), image.shape)
        cached = self._cache.get(key)
        if cached is None:
            cached = Analysis(
                faces=self._detect_faces(image),
                skin_mask=_skin_mask(image),
            )
            if len(self._cache) > 16:  # 简单容量控制
                self._cache.clear()
            self._cache[key] = cached
        return cached

    def pose(self, image: np.ndarray) -> np.ndarray | None:
        """人体姿态关键点 (33,2)，未检测到返回 None。惰性加载模型。"""
        if self._pose is None and _HAS_MEDIAPIPE:
            try:
                self._pose = mp.solutions.pose.Pose(
                    static_image_mode=True, model_complexity=1, min_detection_confidence=0.5
                )
            except Exception:
                return None
        if self._pose is None:
            return None
        key = (id(image), image.shape)
        if key in self._pose_cache:
            return self._pose_cache[key]
        h, w = image.shape[:2]
        result = self._pose.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        points = None
        if result.pose_landmarks:
            points = np.array(
                [(p.x * w, p.y * h) for p in result.pose_landmarks.landmark], dtype=np.float32
            )
        if len(self._pose_cache) > 8:
            self._pose_cache.clear()
        self._pose_cache[key] = points
        return points

    def foreground(self, image: np.ndarray) -> np.ndarray | None:
        """人像前景掩膜 (H,W) uint8（255=前景），用于背景虚化。惰性加载模型。"""
        if self._segmenter is None and _HAS_MEDIAPIPE:
            try:
                self._segmenter = mp.solutions.selfie_segmentation.SelfieSegmentation(
                    model_selection=1
                )
            except Exception:
                return None
        if self._segmenter is None:
            return None
        key = (id(image), image.shape)
        if key in self._seg_cache:
            return self._seg_cache[key]
        result = self._segmenter.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        mask = (np.clip(result.segmentation_mask, 0.0, 1.0) * 255).astype(np.uint8)
        mask = cv2.GaussianBlur(mask, (0, 0), 3)
        if len(self._seg_cache) > 8:
            self._seg_cache.clear()
        self._seg_cache[key] = mask
        return mask

    # ---------- 内部 ----------
    def _detect_faces(self, image: np.ndarray) -> list[Face]:
        if self._mesh is not None:
            return self._detect_mediapipe(image)
        return self._detect_haar(image)

    def _detect_mediapipe(self, image: np.ndarray) -> list[Face]:
        h, w = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        result = self._mesh.process(rgb)
        faces: list[Face] = []
        if not result.multi_face_landmarks:
            return faces
        for lm in result.multi_face_landmarks:
            pts = np.array(
                [(p.x * w, p.y * h) for p in lm.landmark], dtype=np.float32
            )
            xs, ys = pts[:, 0], pts[:, 1]
            x0, y0 = float(xs.min()), float(ys.min())
            x1, y1 = float(xs.max()), float(ys.max())
            faces.append(
                Face(
                    box=(int(x0), int(y0), int(x1 - x0), int(y1 - y0)),
                    landmarks=pts,
                )
            )
        return faces

    def _detect_haar(self, image: np.ndarray) -> list[Face]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detected = self._haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        return [Face(box=tuple(int(v) for v in box)) for box in detected]
