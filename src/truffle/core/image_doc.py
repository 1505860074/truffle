"""图像文档：非破坏式历史（操作列表 + 图像缓存）。

- 记录一串「步骤」(Step)：工具 / 裁剪 / 液化，均可从原图重放；
- `current` = 从原图依次重放 steps[0..pointer-1] 的结果；
- 支持撤销 / 重做 / 跳转 / 删除某步 / 修改某步参数（改后自动重算后续）；
- 具体渲染由外部注入的 `renderer(image, step)` 完成（core 不依赖 tools）。

图像一律 OpenCV 约定：numpy ndarray，BGR，uint8。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np


@dataclass
class Step:
    kind: str  # "tool" | "crop" | "liquify" | "snapshot"
    label: str
    data: dict[str, Any] = field(default_factory=dict)
    origin: str = ""  # "ai" | "manual" | ""


class ImageDocument:
    def __init__(self, max_history: int = 50) -> None:
        self._images: list[np.ndarray | None] = [None]  # images[i] = 应用 steps[0..i-1] 后
        self._steps: list[Step] = []
        self._pointer = 0  # 0..len(steps)
        self._renderer: Callable[[np.ndarray, Step], np.ndarray] | None = None
        self.max_history = max_history
        self.path: Path | None = None

    def set_renderer(self, fn: Callable[[np.ndarray, Step], np.ndarray]) -> None:
        self._renderer = fn

    # ---------- 状态 ----------
    @property
    def is_loaded(self) -> bool:
        return self._images[0] is not None

    @property
    def current(self) -> np.ndarray:
        if self._images[0] is None:
            raise RuntimeError("尚未加载图像")
        return self._images[self._pointer]

    @property
    def original(self) -> np.ndarray:
        if self._images[0] is None:
            raise RuntimeError("尚未加载图像")
        return self._images[0]

    @property
    def can_undo(self) -> bool:
        return self._pointer > 0

    @property
    def can_redo(self) -> bool:
        return self._pointer < len(self._steps)

    def pointer(self) -> int:
        return self._pointer

    def steps(self) -> list[Step]:
        return list(self._steps)

    def step_at(self, index: int) -> Step:
        return self._steps[index]

    # ---------- 读写 ----------
    def load(self, path: str | Path) -> None:
        p = Path(path)
        data = np.fromfile(str(p), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"无法读取图像：{p}")
        self._images = [img.copy()]
        self._steps = []
        self._pointer = 0
        self.path = p

    def set_original(self, image: np.ndarray) -> None:
        self._images = [np.ascontiguousarray(image.copy())]
        self._steps = []
        self._pointer = 0

    def clear(self) -> None:
        """清空到「未加载」状态。"""
        self._images = [None]
        self._steps = []
        self._pointer = 0
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

    # ---------- 步骤 ----------
    def _render(self, base: np.ndarray, step: Step) -> np.ndarray:
        if step.kind == "snapshot" or self._renderer is None:
            return base.copy()
        return self._renderer(base, step)

    def push(self, image: np.ndarray, label: str = "操作", origin: str = "") -> None:
        """快照式入栈（不可重放，仅保留结果）。"""
        self._push_step(Step("snapshot", label, origin=origin), image=image)

    def push_op(
        self, kind: str, label: str, data: dict,
        image: np.ndarray | None = None, origin: str = "",
    ) -> None:
        """可重放的操作入栈；不传 image 则由 renderer 现算。"""
        self._push_step(Step(kind, label, data, origin=origin), image=image)

    def steps_summary(self) -> list[str]:
        """已完成的编辑步骤摘要（区分 AI / 手动），供 agent 上下文使用。"""
        out: list[str] = []
        for i, step in enumerate(self._steps):
            tag = {"ai": "AI", "manual": "手动"}.get(step.origin, "")
            if step.kind == "tool":
                label = f"{step.data.get('name', '')} {step.data.get('params', {})}"
            else:
                label = step.label
            out.append(f"{i + 1}. {label}" + (f"（{tag}）" if tag else ""))
        return out

    def _push_step(self, step: Step, image: np.ndarray | None = None) -> None:
        del self._steps[self._pointer:]
        del self._images[self._pointer + 1:]
        base = self._images[self._pointer]
        result = np.ascontiguousarray(image.copy()) if image is not None else self._render(base, step)
        self._steps.append(step)
        self._images.append(result)
        self._pointer = len(self._steps)
        if len(self._steps) > self.max_history:
            drop = len(self._steps) - self.max_history
            del self._steps[:drop]
            del self._images[1:1 + drop]
            self._pointer = max(0, self._pointer - drop)

    def undo(self) -> bool:
        if self._pointer > 0:
            self._pointer -= 1
            return True
        return False

    def redo(self) -> bool:
        if self._pointer < len(self._steps):
            self._pointer += 1
            return True
        return False

    def jump(self, index: int) -> bool:
        self._pointer = max(0, min(index, len(self._steps)))
        return True

    def reset(self) -> None:
        if self._images[0] is not None:
            self._pointer = 0

    # ---------- 历史树编辑 ----------
    def delete_step(self, index: int) -> None:
        if not (0 <= index < len(self._steps)):
            return
        del self._steps[index]
        del self._images[index + 1]
        self._recompute(index)
        if index < self._pointer:
            self._pointer -= 1
        self._pointer = min(self._pointer, len(self._steps))

    def update_step(self, index: int, data: dict) -> None:
        if not (0 <= index < len(self._steps)):
            return
        self._steps[index].data = data
        self._recompute(index)

    def _recompute(self, start: int) -> None:
        for j in range(start, len(self._steps)):
            self._images[j + 1] = self._render(self._images[j], self._steps[j])
