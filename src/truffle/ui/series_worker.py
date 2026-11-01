"""成套图后台处理：逐图求解风格 + 生成拼图 + 批量导出。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from ..agent.series import contact_sheet, export_batch
from ..agent.solver import ParamSolver
from ..agent.style import resolve_style
from ..cv.analyzer import Analyzer
from ..tools.pipeline import render_pipeline
from ..tools.registry import ToolRegistry


class SeriesWorker(QThread):
    progress = Signal(int, int)
    previewReady = Signal(object)
    exported = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        paths: list[str],
        registry: ToolRegistry,
        analyzer: Analyzer,
        style_id: str,
        *,
        columns: int = 3,
        out_dir: str = "",
        ext: str = ".jpg",
        quality: int = 92,
        long_side: int = 1080,
        center_text: str = "",
        avatar_path: str = "",
    ) -> None:
        super().__init__()
        self.paths = paths
        self.registry = registry
        self.analyzer = analyzer
        self.style_id = style_id
        self.columns = columns
        self.out_dir = out_dir
        self.ext = ext
        self.quality = quality
        self.long_side = long_side
        self.center_text = center_text
        self.avatar_path = avatar_path

    def run(self) -> None:
        try:
            profile = resolve_style(self.style_id)
            solver = ParamSolver(
                self.registry, self.analyzer,
                preview_max=512, max_iterations=1, max_evaluations=6,
            )
            styled: list[np.ndarray] = []
            total = len(self.paths)
            for index, path in enumerate(self.paths, 1):
                data = np.fromfile(path, dtype=np.uint8)
                image = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if image is None:
                    continue
                try:
                    result = solver.solve(image, profile)
                    out = render_pipeline(self.registry, self.analyzer, image, result.jobs) if result.jobs else image
                except Exception:
                    out = image
                styled.append(out)
                self.progress.emit(index, total)
            if not styled:
                self.failed.emit("没有可处理的图片")
                return
            avatar = None
            if self.avatar_path:
                raw = np.fromfile(self.avatar_path, dtype=np.uint8)
                avatar = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            sheet = contact_sheet(
                styled,
                columns=self.columns,
                center_text=self.center_text,
                center_avatar=avatar,
            )
            self.previewReady.emit(sheet)
            if self.out_dir:
                paths = export_batch(
                    styled,
                    self.out_dir,
                    prefix=Path(self.paths[0]).stem if self.paths else "truffle",
                    ext=self.ext,
                    quality=self.quality,
                    long_side=self.long_side,
                )
                self.exported.emit(paths)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
