"""图像文档模型：当前图、原图、撤销/重做栈、文件读写。

图像一律使用 OpenCV 约定：numpy ndarray，BGR 顺序，uint8。
所有修改都是「返回新图」，不原地改动，方便撤销与 A/B 对比。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


class ImageDocument:
    def __init__(self, max_history: int = 30) -> None:
        self._original: np.ndarray | None = None
        self._current: np.ndarray | None = None
        self._undo: list[np.ndarray] = []
        self._redo: list[np.ndarray] = []
        self.max_history = max_history
        self.path: Path | None = None

    # ---------- 状态 ----------
    @property
    def is_loaded(self) -> bool:
        return self._current is not None

    @property
    def current(self) -> np.ndarray:
        if self._current is None:
            raise RuntimeError("尚未加载图像")
        return self._current

    @property
    def original(self) -> np.ndarray:
        if self._original is None:
            raise RuntimeError("尚未加载图像")
        return self._original

    @property
    def can_undo(self) -> bool:
        return len(self._undo) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo) > 0

    # ---------- 读写 ----------
    def load(self, path: str | Path) -> None:
        p = Path(path)
        # 用 imdecode 读，避免中文路径问题
        data = np.fromfile(str(p), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"无法读取图像：{p}")
        self._original = img.copy()
        self._current = img.copy()
        self._undo.clear()
        self._redo.clear()
        self.path = p

    def save(self, path: str | Path) -> None:
        p = Path(path)
        ext = p.suffix or ".png"
        ok, buf = cv2.imencode(ext, self.current)
        if not ok:
            raise ValueError(f"无法编码图像：{ext}")
        buf.tofile(str(p))
        self.path = p

    # ---------- 编辑 ----------
    def push(self, image: np.ndarray) -> None:
        """记录一步新状态（非破坏式）。"""
        if self._current is not None:
            self._undo.append(self._current)
            if len(self._undo) > self.max_history:
                self._undo.pop(0)
        self._current = np.ascontiguousarray(image.copy())
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._current)
        self._current = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._current)
        self._current = self._redo.pop()
        return True

    def reset(self) -> None:
        """回到原图状态。"""
        if self._original is None:
            return
        self.push(self._original)
