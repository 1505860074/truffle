"""图层模型：RGBA 图层 + 混合模式 + 不透明度 + 图层蒙版。

约定：
- 图层像素统一为 BGRA（uint8），画布尺寸一致；
- 图层对象按「不可变」使用：修改时用 dataclasses.replace 生成新对象，
  这样历史快照可以安全共享未改动的数组，避免整栈深拷贝；
- 合成结果为 BGR（uint8），默认铺在白底上，便于显示与导出。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

import cv2
import numpy as np

BLEND_MODES: tuple[str, ...] = (
    "normal", "multiply", "screen", "overlay",
    "darken", "lighten", "add", "subtract", "difference",
)

BLEND_LABELS: dict[str, str] = {
    "normal": "正常",
    "multiply": "正片叠底",
    "screen": "滤色",
    "overlay": "叠加",
    "darken": "变暗",
    "lighten": "变亮",
    "add": "线性减淡（添加）",
    "subtract": "减去",
    "difference": "差值",
}


def ensure_bgra(image: np.ndarray) -> np.ndarray:
    """把 BGR / BGRA / 灰度图统一成连续 BGRA。"""
    if image is None:
        raise ValueError("图像为空")
    arr = np.asarray(image)
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    if arr.ndim == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGRA)
    elif arr.ndim == 3 and arr.shape[2] == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2BGRA)
    elif arr.ndim == 3 and arr.shape[2] == 4:
        pass
    else:
        raise ValueError(f"不支持的图像形状：{arr.shape}")
    return np.ascontiguousarray(arr)


def split_bgra(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    bgra = ensure_bgra(image)
    return np.ascontiguousarray(bgra[..., :3]), np.ascontiguousarray(bgra[..., 3])


def alpha_over(bottom: np.ndarray, top: np.ndarray) -> np.ndarray:
    """标准 source-over 合成（BGRA 输出）。"""
    b = ensure_bgra(bottom).astype(np.float32)
    t = ensure_bgra(top).astype(np.float32)
    ta = t[..., 3:4] / 255.0
    ba = b[..., 3:4] / 255.0
    out_a = ta + ba * (1.0 - ta)
    safe = np.maximum(out_a, 1e-6)
    out_rgb = (t[..., :3] * ta + b[..., :3] * ba * (1.0 - ta)) / safe
    out = np.empty_like(b)
    out[..., :3] = out_rgb
    out[..., 3:4] = out_a * 255.0
    return np.clip(out, 0, 255).astype(np.uint8)


def _blend(name: str, dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """对 0..255 float32 的 BGR 做混合，返回同形状。"""
    if name == "multiply":
        return dst * src / 255.0
    if name == "screen":
        return 255.0 - (255.0 - dst) * (255.0 - src) / 255.0
    if name == "overlay":
        low = 2.0 * dst * src / 255.0
        high = 255.0 - 2.0 * (255.0 - dst) * (255.0 - src) / 255.0
        return np.where(dst < 128.0, low, high)
    if name == "darken":
        return np.minimum(dst, src)
    if name == "lighten":
        return np.maximum(dst, src)
    if name == "add":
        return np.minimum(255.0, dst + src)
    if name == "subtract":
        return np.maximum(0.0, dst - src)
    if name == "difference":
        return np.abs(dst - src)
    return src


@dataclass
class Layer:
    id: int
    name: str
    image: np.ndarray  # BGRA, uint8, 与画布同尺寸
    visible: bool = True
    opacity: float = 1.0
    blend: str = "normal"
    mask: np.ndarray | None = None  # uint8, 与画布同尺寸；255=完全可见
    locked: bool = False

    # ---------- 便捷视图 ----------
    @property
    def size(self) -> tuple[int, int]:
        h, w = self.image.shape[:2]
        return w, h

    @property
    def bgr(self) -> np.ndarray:
        return np.ascontiguousarray(self.image[..., :3])

    @property
    def alpha(self) -> np.ndarray:
        return self.image[..., 3]

    def clone(self) -> "Layer":
        """深拷贝图层（用于需要独立修改像素的场景）。"""
        return replace(
            self,
            image=self.image.copy(),
            mask=None if self.mask is None else self.mask.copy(),
        )

    def effective_alpha(self) -> np.ndarray:
        alpha = self.image[..., 3].astype(np.float32) / 255.0
        if self.mask is not None and self.mask.shape[:2] == alpha.shape[:2]:
            alpha *= self.mask.astype(np.float32) / 255.0
        return np.clip(alpha * float(self.opacity), 0.0, 1.0)

    def thumbnail(self, size: int = 40) -> np.ndarray:
        """返回 BGRA 缩略图（用于图层面板）。"""
        h, w = self.image.shape[:2]
        if h <= 0 or w <= 0:
            return np.zeros((size, size, 4), dtype=np.uint8)
        scale = size / max(h, w)
        tw, th = max(1, int(w * scale)), max(1, int(h * scale))
        small = cv2.resize(self.image, (tw, th), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((size, size, 4), dtype=np.uint8)
        x, y = (size - tw) // 2, (size - th) // 2
        canvas[y:y + th, x:x + tw] = small
        return canvas


class LayerStack:
    """图层栈：底 → 顶排列，负责合成与常规图层操作。"""

    def __init__(self) -> None:
        self.layers: list[Layer] = []
        self.active_index: int = 0

    # ---------- 状态 ----------
    @property
    def is_loaded(self) -> bool:
        return bool(self.layers)

    @property
    def active(self) -> Layer | None:
        if not self.layers:
            return None
        return self.layers[max(0, min(self.active_index, len(self.layers) - 1))]

    def size(self) -> tuple[int, int]:
        if not self.layers:
            return 0, 0
        return self.layers[0].size

    def find(self, layer_id: int) -> int:
        for i, layer in enumerate(self.layers):
            if layer.id == layer_id:
                return i
        return -1

    def set_active(self, index: int) -> None:
        if self.layers:
            self.active_index = max(0, min(int(index), len(self.layers) - 1))

    # ---------- 合成 ----------
    def composite(self, background: tuple[int, int, int] = (255, 255, 255)) -> np.ndarray:
        if not self.layers:
            return np.zeros((0, 0, 3), dtype=np.uint8)
        w, h = self.size()
        out = np.empty((h, w, 3), dtype=np.float32)
        out[:] = np.array(background, dtype=np.float32)
        for layer in self.layers:
            if not layer.visible or layer.opacity <= 0.0:
                continue
            if (layer.blend == "normal" and layer.opacity >= 0.999
                    and layer.mask is None and np.all(layer.image[..., 3] == 255)):
                # 常见路径：不透明普通图层直接覆盖，避免大图产生多份浮点临时数组
                out[:] = layer.image[..., :3]
                continue
            src = layer.image[..., :3].astype(np.float32)
            alpha = layer.effective_alpha()
            if not np.any(alpha > 0):
                continue
            if layer.blend == "normal":
                blended = src
            else:
                blended = _blend(layer.blend, out, src)
            a = alpha[..., None]
            out = out * (1.0 - a) + blended * a
        return np.clip(out, 0, 255).astype(np.uint8)

    # ---------- 操作（返回新图层列表，便于快照共享） ----------
    def add_layer(self, layer: Layer, index: int | None = None) -> Layer:
        if index is None:
            index = len(self.layers)
        self.layers.insert(index, layer)
        self.active_index = index
        return layer

    def remove_layer(self, index: int) -> None:
        if not self.layers:
            return
        index = max(0, min(index, len(self.layers) - 1))
        del self.layers[index]
        self.active_index = max(0, min(index - 1, len(self.layers) - 1))

    def move_layer(self, index: int, delta: int) -> int:
        if not self.layers:
            return 0
        target = max(0, min(index + delta, len(self.layers) - 1))
        if target == index:
            return index
        layer = self.layers.pop(index)
        self.layers.insert(target, layer)
        self.active_index = target
        return target

    def merge_down(self, index: int) -> bool:
        if index <= 0 or index >= len(self.layers):
            return False
        lower = self.layers[index - 1]
        upper = self.layers[index]

        def _apply(layer: Layer) -> np.ndarray:
            img = layer.image.copy()
            alpha = layer.effective_alpha()
            img[..., 3] = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)
            return img

        merged = alpha_over(_apply(lower), _apply(upper))
        self.layers[index - 1] = replace(
            lower, image=merged, mask=None, opacity=1.0, blend="normal"
        )
        del self.layers[index]
        self.active_index = index - 1
        return True

    def flatten(self) -> np.ndarray:
        return self.composite()

    def crop(self, x: int, y: int, w: int, h: int) -> None:
        x, y, w, h = int(x), int(y), int(w), int(h)
        for i, layer in enumerate(self.layers):
            lh, lw = layer.image.shape[:2]
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(lw, x + w), min(lh, y + h)
            img = layer.image[y0:y1, x0:x1]
            mask = None if layer.mask is None else layer.mask[y0:y1, x0:x1]
            self.layers[i] = replace(
                layer,
                image=np.ascontiguousarray(img),
                mask=None if mask is None else np.ascontiguousarray(mask),
            )

    def resize_canvas(self, w: int, h: int, anchor: tuple[int, int] = (0, 0)) -> None:
        """改变画布尺寸（anchor 为旧内容在新画布中的左上角偏移）。"""
        ax, ay = anchor
        for i, layer in enumerate(self.layers):
            canvas = np.zeros((h, w, 4), dtype=np.uint8)
            src = layer.image
            sh, sw = src.shape[:2]
            x0, y0 = max(0, ax), max(0, ay)
            x1, y1 = min(w, ax + sw), min(h, ay + sh)
            sx0, sy0 = x0 - ax, y0 - ay
            canvas[y0:y1, x0:x1] = src[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
            mask = None
            if layer.mask is not None:
                mask = np.zeros((h, w), dtype=np.uint8)
                mask[y0:y1, x0:x1] = layer.mask[
                    sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)
                ]
            self.layers[i] = replace(layer, image=canvas, mask=mask)


def blend_function(name: str) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    return lambda dst, src: _blend(name, dst.astype(np.float32), src.astype(np.float32))
