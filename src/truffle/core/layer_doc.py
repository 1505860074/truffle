"""图层文档：多图层 + 快照式历史 + 兼容原 ImageDocument 的常用接口。

设计取舍：
- 历史记录「每一步之后的完整图层状态」；未改动的图层数组在快照间共享引用，
  所以多图层、多步骤也不会成倍占用内存；
- 与 `ImageDocument` 不同，历史以「状态」而非「可重放操作」为主，
  更贴近 Photoshop 的历史面板（可跳回任意状态、从该状态继续编辑并分叉）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from .image_doc import Step
from .layers import BLEND_MODES, Layer, LayerStack, ensure_bgra, split_bgra
from .selection import multiply_alpha
from .transform import transform_layer


class LayerDocument:
    def __init__(self, max_history: int = 100) -> None:
        self.path: Path | None = None
        self.max_history = max_history
        self._stack = LayerStack()
        self._steps: list[Step] = []
        self._snapshots: list[tuple[tuple[Layer, ...], int]] = []
        self._pointer = 0
        self._renderer: Callable[[np.ndarray, Step], np.ndarray] | None = None
        self._original: np.ndarray | None = None
        self._composite: np.ndarray | None = None
        self._next_id = 1
        self.history_readonly = False

    # ---------- 兼容接口 ----------
    @property
    def is_loaded(self) -> bool:
        return self._stack.is_loaded

    @property
    def current(self) -> np.ndarray:
        if not self.is_loaded:
            raise RuntimeError("尚未加载图像")
        if self._composite is None:
            self._composite = self._stack.composite()
        return self._composite

    @property
    def original(self) -> np.ndarray:
        if self._original is None:
            raise RuntimeError("尚未加载图像")
        return self._original

    @property
    def can_undo(self) -> bool:
        return self._pointer > 0

    @property
    def can_redo(self) -> bool:
        return self._pointer < len(self._steps)

    @property
    def active_index(self) -> int:
        return self._stack.active_index

    @property
    def active_layer(self) -> Layer | None:
        return self._stack.active

    def layers(self) -> list[Layer]:
        return list(self._stack.layers)

    def width(self) -> int:
        return self._stack.size()[0]

    def height(self) -> int:
        return self._stack.size()[1]

    def pointer(self) -> int:
        return self._pointer

    def steps(self) -> list[Step]:
        return list(self._steps)

    def step_at(self, index: int) -> Step:
        return self._steps[index]

    def history_state(self) -> dict:
        """Serializable in-memory state used by the project layer."""
        return {
            "original": None if self._original is None else self._original,
            "layers": list(self._stack.layers),
            "steps": list(self._steps),
            "snapshots": list(self._snapshots),
            "pointer": self._pointer,
            "next_id": self._next_id,
            "max_history": self.max_history,
        }

    def restore_history_state(
        self,
        original: np.ndarray | None,
        layers: list[Layer],
        steps: list[Step],
        snapshots: list[tuple[tuple[Layer, ...], int]],
        pointer: int,
        next_id: int,
        max_history: int = 100,
        active_index: int = 0,
    ) -> None:
        self.max_history = max(1, int(max_history))
        self._stack = LayerStack()
        self._stack.layers = list(layers)
        self._stack.active_index = max(0, min(int(active_index), len(layers) - 1)) if layers else 0
        self._steps = list(steps)
        self._snapshots = list(snapshots)
        self._pointer = max(0, min(int(pointer), len(self._steps)))
        self._next_id = max(1, int(next_id))
        self._original = None if original is None else np.ascontiguousarray(original)
        self._composite = None
        self.history_readonly = True

    def set_renderer(self, fn: Callable[[np.ndarray, Step], np.ndarray]) -> None:
        self._renderer = fn

    # ---------- 载入 / 保存 ----------
    def load(self, path: str | Path) -> None:
        p = Path(path)
        data = np.fromfile(str(p), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"无法读取图像：{p}")
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        self._init_with(img, "背景")
        self.path = p
        self._original = np.ascontiguousarray(img.copy())

    def set_original(self, image: np.ndarray) -> None:
        img = np.asarray(image)
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        self._init_with(np.ascontiguousarray(img), "背景")
        self._original = np.ascontiguousarray(img.copy())

    def _init_with(self, bgr: np.ndarray, name: str) -> None:
        layer = Layer(self._new_id(), name, ensure_bgra(bgr))
        self._stack = LayerStack()
        self._stack.add_layer(layer)
        self._steps = []
        self._snapshots = [(tuple(self._stack.layers), self._stack.active_index)]
        self._pointer = 0
        self._composite = None
        self._original = np.ascontiguousarray(bgr.copy())

    def clear(self) -> None:
        self._stack = LayerStack()
        self._steps = []
        self._snapshots = []
        self._pointer = 0
        self._original = None
        self._composite = None
        self.path = None

    def save(self, path: str | Path, image: np.ndarray | None = None) -> None:
        p = Path(path)
        ext = p.suffix or ".png"
        data = self.current if image is None else image
        ok, buf = cv2.imencode(ext, data)
        if not ok:
            raise ValueError(f"无法编码图像：{ext}")
        buf.tofile(str(p))
        self.path = p

    # ---------- 历史 ----------
    def _capture(self) -> tuple[tuple[Layer, ...], int]:
        return tuple(self._stack.layers), self._stack.active_index

    def _restore(self, snapshot: tuple[tuple[Layer, ...], int]) -> None:
        layers, active = snapshot
        self._stack.layers = list(layers)
        self._stack.active_index = max(0, min(active, len(layers) - 1))
        self._invalidate()

    def _invalidate(self) -> None:
        self._composite = None

    def _push(self, step: Step) -> None:
        del self._steps[self._pointer:]
        del self._snapshots[self._pointer + 1:]
        self._steps.append(step)
        self._snapshots.append(self._capture())
        self._pointer = len(self._steps)
        self._trim()
        self._invalidate()

    def _trim(self) -> None:
        if len(self._steps) <= self.max_history:
            return
        drop = len(self._steps) - self.max_history
        del self._steps[:drop]
        del self._snapshots[1:1 + drop]
        self._pointer = max(0, self._pointer - drop)

    def _truncate(self, index: int) -> None:
        del self._steps[index:]
        del self._snapshots[index + 1:]

    def undo(self) -> bool:
        if self._pointer <= 0:
            return False
        self._pointer -= 1
        self._restore(self._snapshots[self._pointer])
        return True

    def redo(self) -> bool:
        if self._pointer >= len(self._steps):
            return False
        self._pointer += 1
        self._restore(self._snapshots[self._pointer])
        return True

    def jump(self, index: int) -> bool:
        self._pointer = max(0, min(int(index), len(self._steps)))
        if self._pointer < len(self._snapshots):
            self._restore(self._snapshots[self._pointer])
        return True

    def reset(self) -> None:
        if self.is_loaded:
            self.jump(0)

    def delete_step(self, index: int) -> None:
        """删除某步及其之后的步骤（回到该步之前的状态）。"""
        if not (0 <= index < len(self._steps)):
            return
        self._restore(self._snapshots[index])
        self._truncate(index)
        self._pointer = index

    def update_step(self, index: int, data: dict) -> None:
        """修改工具 / 裁剪步骤：丢弃该步之后的历史，重新计算这一步。"""
        if not (0 <= index < len(self._steps)):
            return
        step = self._steps[index]
        self._restore(self._snapshots[index])
        new_data = dict(data)
        new_step = Step(step.kind, step.label, new_data, origin=step.origin)
        if step.kind == "tool" and new_data.get("name") == "rotate_flip":
            self._apply_rotate_flip(new_data.get("params", {}))
        elif step.kind == "tool" and self._renderer is not None:
            layer_id = new_data.get("layer")
            idx = self._stack.find(int(layer_id)) if layer_id is not None else -1
            if idx < 0:
                idx = self._stack.active_index
            if 0 <= idx < len(self._stack.layers):
                self._apply_tool_to_layer(idx, new_step, None)
        elif step.kind == "crop":
            x, y, w, h = new_data.get("rect", (0, 0, 0, 0))
            self._stack.crop(int(x), int(y), int(w), int(h))
        self._truncate(index)
        self._steps.append(new_step)
        self._snapshots.append(self._capture())
        self._pointer = index + 1
        self._invalidate()

    # ---------- 步骤 / 操作 ----------
    def push(self, image: np.ndarray, label: str = "操作", origin: str = "") -> None:
        """用整张图替换当前图层（兼容旧接口）。"""
        if not self.is_loaded:
            return
        self._replace_active_bgra(ensure_bgra(image))
        self._push(Step("snapshot", label, origin=origin))

    def push_op(
        self, kind: str, label: str, data: dict,
        image: np.ndarray | None = None, origin: str = "",
    ) -> None:
        if not self.is_loaded:
            return
        data = dict(data)
        if kind == "crop" and "rect" in data:
            x, y, w, h = [int(v) for v in data["rect"]]
            self._stack.crop(x, y, w, h)
        elif kind in ("tool", "liquify") and image is None:
            if kind == "tool" and data.get("name") == "rotate_flip":
                self._apply_rotate_flip(data.get("params", {}))
            else:
                idx = self._stack.active_index
                layer_id = data.get("layer")
                if layer_id is not None:
                    found = self._stack.find(int(layer_id))
                    if found >= 0:
                        idx = found
                self._apply_tool_to_layer(idx, Step(kind, label, data, origin), data.get("mask"))
        elif kind == "transform" and image is None:
            self.transform_active(
                data.get("src_rect"), data.get("dst_quad"), data.get("mask"),
                label=label, record=False,
            )
        elif image is not None:
            self._set_active_from_bgr(image)
        self._push(Step(kind, label, data, origin=origin))

    def _apply_tool_to_layer(self, index: int, step: Step, mask: np.ndarray | None) -> None:
        if not (0 <= index < len(self._stack.layers)):
            return
        layer = self._stack.layers[index]
        if self._renderer is None:
            return
        rendered = self._renderer(layer.bgr, step)
        if rendered is None:
            return
        if rendered.shape[:2] != layer.image.shape[:2]:
            # 旋转等改变尺寸的工具：退化为单图层文档，避免画布与图层尺寸不一致
            self._stack.layers = [Layer(layer.id, layer.name, ensure_bgra(rendered))]
            self._stack.active_index = 0
            return
        alpha = layer.image[..., 3]
        new_img = np.dstack([rendered[..., :3], alpha]).astype(np.uint8)
        self._stack.layers[index] = Layer(
            layer.id, layer.name, np.ascontiguousarray(new_img),
            visible=layer.visible, opacity=layer.opacity,
            blend=layer.blend, mask=layer.mask, locked=layer.locked,
        )

    def _set_active_from_bgr(self, image: np.ndarray) -> None:
        layer = self._stack.active
        if layer is None:
            return
        new = ensure_bgra(image)
        if new.shape[:2] != layer.image.shape[:2]:
            self._stack.layers = [Layer(layer.id, layer.name, new)]
            self._stack.active_index = 0
            return
        if np.asarray(image).ndim == 3 and np.asarray(image).shape[2] == 3:
            new[..., 3] = layer.image[..., 3]
        self._stack.layers[self._stack.active_index] = Layer(
            layer.id, layer.name, np.ascontiguousarray(new),
            visible=layer.visible, opacity=layer.opacity,
            blend=layer.blend, mask=layer.mask, locked=layer.locked,
        )
        self._invalidate()

    def _replace_active_bgra(self, image_bgra: np.ndarray) -> None:
        layer = self._stack.active
        if layer is None:
            return
        new = ensure_bgra(image_bgra)
        if new.shape[:2] != layer.image.shape[:2]:
            self._stack.layers = [Layer(layer.id, layer.name, new)]
            self._stack.active_index = 0
        else:
            self._stack.layers[self._stack.active_index] = Layer(
                layer.id, layer.name, np.ascontiguousarray(new),
                visible=layer.visible, opacity=layer.opacity,
                blend=layer.blend, mask=layer.mask, locked=layer.locked,
            )
        self._invalidate()

    def composite_with_active(self, image_bgra: np.ndarray) -> np.ndarray:
        """用给定像素临时替换活动图层后合成（不写入文档/历史）。"""
        if not self.is_loaded:
            return np.zeros((0, 0, 3), dtype=np.uint8)
        layers = list(self._stack.layers)
        layer = layers[self._stack.active_index]
        layers[self._stack.active_index] = Layer(
            layer.id, layer.name, ensure_bgra(image_bgra), layer.visible,
            layer.opacity, layer.blend, layer.mask, layer.locked,
        )
        stack = LayerStack()
        stack.layers = layers
        return stack.composite()

    def record(self, label: str = "图层状态") -> None:
        """把当前图层状态记入历史（用于滑块拖动结束等场景）。"""
        if self.is_loaded:
            self._push(Step("layer", label, {}))

    # ---------- AI / 工具接口 ----------
    def tool_source(self) -> np.ndarray:
        """AI 工具的作用对象：当前活动图层的 BGR。"""
        layer = self._stack.active
        if layer is None:
            return self.current
        return layer.bgr

    def commit_tool(self, name: str, params: dict, image: np.ndarray, origin: str = "ai") -> None:
        if not self.is_loaded:
            return
        data = {"name": name, "params": params, "layer": self._stack.active.id}
        if name == "rotate_flip":
            self._apply_rotate_flip(params)
        else:
            self._set_active_from_bgr(image)
        self._push(Step("tool", name, data, origin=origin))

    def _apply_rotate_flip(self, params: dict) -> None:
        """??/??????????????????????"""
        rotate = int(params.get("rotate", 0) or 0)
        flip = str(params.get("flip", "none") or "none")

        def convert(image: np.ndarray) -> np.ndarray:
            out = image
            if rotate in (90, 180, 270):
                k = {90: 3, 180: 2, 270: 1}[rotate]
                out = np.ascontiguousarray(np.rot90(out, k))
            if flip == "horizontal":
                out = cv2.flip(out, 1)
            elif flip == "vertical":
                out = cv2.flip(out, 0)
            return np.ascontiguousarray(out)

        for i, layer in enumerate(self._stack.layers):
            mask = None if layer.mask is None else convert(layer.mask)
            self._stack.layers[i] = Layer(
                layer.id, layer.name, convert(layer.image), layer.visible,
                layer.opacity, layer.blend, mask, layer.locked,
            )
        if self._original is not None:
            self._original = convert(self._original)
        self._invalidate()

    # ---------- 图层操作 ----------
    def _new_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def add_layer(self, name: str | None = None, image: np.ndarray | None = None,
                  label: str | None = None) -> Layer:
        w, h = self._stack.size()
        if image is None:
            img = np.zeros((h, w, 4), dtype=np.uint8)
        else:
            img = ensure_bgra(image)
        layer = Layer(self._new_id(), name or f"图层 {len(self._stack.layers) + 1}", img)
        self._stack.add_layer(layer, self._stack.active_index + 1)
        self._invalidate()
        self._push(Step("layer", label or "新建图层", {}))
        return layer

    def duplicate_active_layer(self) -> None:
        layer = self._stack.active
        if layer is None:
            return
        copy = layer.clone()
        copy = Layer(self._new_id(), f"{layer.name} 副本", copy.image, copy.visible,
                     copy.opacity, copy.blend, copy.mask, copy.locked)
        self._stack.add_layer(copy, self._stack.active_index + 1)
        self._invalidate()
        self._push(Step("layer", "复制图层", {}))

    def layer_via_copy(self, mask: np.ndarray | None) -> None:
        """Ctrl+J：把选区内的像素复制到新图层（无选区则复制整层）。"""
        layer = self._stack.active
        if layer is None:
            return
        if mask is None:
            self.duplicate_active_layer()
            return
        img = layer.image.copy()
        if mask.shape[:2] != img.shape[:2]:
            mask = cv2.resize(mask, (img.shape[1], img.shape[0]),
                              interpolation=cv2.INTER_NEAREST)
        img[..., 3] = np.clip(
            img[..., 3].astype(np.float32) * (mask.astype(np.float32) / 255.0),
            0, 255,
        ).astype(np.uint8)
        copy = Layer(self._new_id(), f"{layer.name} 的拷贝", img)
        self._stack.add_layer(copy, self._stack.active_index + 1)
        self._invalidate()
        self._push(Step("layer", "通过拷贝的图层", {}))

    def delete_active_layer(self) -> None:
        if len(self._stack.layers) <= 1:
            return
        self._stack.remove_layer(self._stack.active_index)
        self._invalidate()
        self._push(Step("layer", "删除图层", {}))

    def move_active_layer(self, delta: int) -> None:
        self._stack.move_layer(self._stack.active_index, delta)
        self._invalidate()
        self._push(Step("layer", "调整图层顺序", {}))

    def merge_down(self) -> None:
        if self._stack.merge_down(self._stack.active_index):
            self._invalidate()
            self._push(Step("layer", "向下合并", {}))

    def flatten_layers(self) -> None:
        if not self.is_loaded:
            return
        flat = self.current
        self._stack = LayerStack()
        self._stack.add_layer(Layer(self._new_id(), "背景", ensure_bgra(flat)))
        self._invalidate()
        self._push(Step("layer", "合并可见图层", {}))

    def set_layer_visible(self, index: int, visible: bool, record: bool = True) -> None:
        if not (0 <= index < len(self._stack.layers)):
            return
        layer = self._stack.layers[index]
        self._stack.layers[index] = Layer(
            layer.id, layer.name, layer.image, bool(visible), layer.opacity,
            layer.blend, layer.mask, layer.locked,
        )
        self._invalidate()
        if record:
            self._push(Step("layer", "显示/隐藏图层", {}))

    def set_layer_opacity(self, index: int, opacity: float, record: bool = True) -> None:
        if not (0 <= index < len(self._stack.layers)):
            return
        layer = self._stack.layers[index]
        self._stack.layers[index] = Layer(
            layer.id, layer.name, layer.image, layer.visible,
            max(0.0, min(1.0, float(opacity))), layer.blend, layer.mask, layer.locked,
        )
        self._invalidate()
        if record:
            self._push(Step("layer", "调整不透明度", {}))

    def set_layer_blend(self, index: int, blend: str, record: bool = True) -> None:
        if not (0 <= index < len(self._stack.layers)):
            return
        if blend not in BLEND_MODES:
            return
        layer = self._stack.layers[index]
        self._stack.layers[index] = Layer(
            layer.id, layer.name, layer.image, layer.visible,
            layer.opacity, blend, layer.mask, layer.locked,
        )
        self._invalidate()
        if record:
            self._push(Step("layer", "更改混合模式", {}))

    def set_active_layer(self, index: int) -> None:
        self._stack.set_active(index)

    def rename_layer(self, index: int, name: str) -> None:
        if not (0 <= index < len(self._stack.layers)):
            return
        layer = self._stack.layers[index]
        self._stack.layers[index] = Layer(
            layer.id, name, layer.image, layer.visible,
            layer.opacity, layer.blend, layer.mask, layer.locked,
        )

    def add_mask_from_selection(self, mask: np.ndarray | None) -> None:
        layer = self._stack.active
        if layer is None or mask is None:
            return
        if mask.shape[:2] != layer.image.shape[:2]:
            mask = cv2.resize(mask, (layer.image.shape[1], layer.image.shape[0]),
                              interpolation=cv2.INTER_NEAREST)
        self._stack.layers[self._stack.active_index] = Layer(
            layer.id, layer.name, layer.image, layer.visible, layer.opacity,
            layer.blend, mask.copy(), layer.locked,
        )
        self._invalidate()
        self._push(Step("layer", "添加图层蒙版", {}))

    def delete_mask(self) -> None:
        layer = self._stack.active
        if layer is None or layer.mask is None:
            return
        self._stack.layers[self._stack.active_index] = Layer(
            layer.id, layer.name, layer.image, layer.visible, layer.opacity,
            layer.blend, None, layer.locked,
        )
        self._invalidate()
        self._push(Step("layer", "删除图层蒙版", {}))

    # ---------- 像素变换 ----------
    def transform_active(self, src_rect, dst_quad, selection: np.ndarray | None,
                         label: str = "自由变换", record: bool = True) -> None:
        layer = self._stack.active
        if layer is None or src_rect is None or dst_quad is None:
            return
        result = transform_layer(layer.image, tuple(int(v) for v in src_rect), dst_quad, selection)
        self._stack.layers[self._stack.active_index] = Layer(
            layer.id, layer.name, np.ascontiguousarray(result), layer.visible,
            layer.opacity, layer.blend, layer.mask, layer.locked,
        )
        self._invalidate()
        if record:
            data = {"src_rect": tuple(int(v) for v in src_rect),
                    "dst_quad": [(float(x), float(y)) for x, y in dst_quad]}
            self._push(Step("transform", label, data))

    def translate_active(self, dx: float, dy: float) -> None:
        layer = self._stack.active
        if layer is None:
            return
        h, w = layer.image.shape[:2]
        matrix = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
        moved = cv2.warpAffine(
            layer.image, matrix, (w, h), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0),
        )
        moved_mask = layer.mask
        if moved_mask is not None:
            moved_mask = cv2.warpAffine(
                moved_mask, matrix, (w, h), flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT, borderValue=0,
            )
        self._stack.layers[self._stack.active_index] = Layer(
            layer.id, layer.name, np.ascontiguousarray(moved), layer.visible,
            layer.opacity, layer.blend, moved_mask, layer.locked,
        )
        self._invalidate()
        self._push(Step("transform", "移动图层", {"dx": dx, "dy": dy}))

    def flip_active(self, horizontal: bool = True, vertical: bool = False) -> None:
        layer = self._stack.active
        if layer is None:
            return
        code = None
        if horizontal and vertical:
            code = -1
        elif horizontal:
            code = 1
        elif vertical:
            code = 0
        if code is None:
            return
        flipped = cv2.flip(layer.image, code)
        flipped_mask = None if layer.mask is None else cv2.flip(layer.mask, code)
        self._stack.layers[self._stack.active_index] = Layer(
            layer.id, layer.name, np.ascontiguousarray(flipped), layer.visible,
            layer.opacity, layer.blend, flipped_mask, layer.locked,
        )
        self._invalidate()
        self._push(Step("transform", "翻转图层", {"h": horizontal, "v": vertical}))

    # ---------- 辅助 ----------
    @staticmethod
    def _crop_image(image: np.ndarray | None, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        if image is None:
            return None
        H, W = image.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        if x1 <= x0 or y1 <= y0:
            return image
        return np.ascontiguousarray(image[y0:y1, x0:x1])

    def steps_summary(self) -> list[str]:
        out: list[str] = []
        for i, step in enumerate(self._steps):
            tag = {"ai": "AI", "manual": "手动"}.get(step.origin, "")
            if step.kind == "tool":
                label = f"{step.data.get('name', '')} {step.data.get('params', {})}"
            else:
                label = step.label
            out.append(f"{i + 1}. {label}" + (f"（{tag}）" if tag else ""))
        return out

    def apply_selection_mask(self, mask: np.ndarray | None) -> None:
        """把选区作为当前图层的透明蒙版（用于抠图到新图层）。"""
        layer = self._stack.active
        if layer is None:
            return
        self._stack.layers[self._stack.active_index] = Layer(
            layer.id, layer.name, multiply_alpha(layer.image, mask), layer.visible,
            layer.opacity, layer.blend, layer.mask, layer.locked,
        )
        self._invalidate()


def bgra_to_bgr(image: np.ndarray) -> np.ndarray:
    return split_bgra(image)[0]
