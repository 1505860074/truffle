"""视频修饰：逐帧套用图像工具管线并写出视频。

- 复用 `tools.pipeline.render_pipeline`，与图片同一套工具/参数；
- 大分辨率会先缩到「最长边上限」再处理（提速），输出尺寸随之；
- 注意：OpenCV 写视频不含音轨（本工具只处理画面）。
"""

from __future__ import annotations

from typing import Any, Callable

import cv2
import numpy as np

from ..cv.analyzer import Analyzer
from ..tools.pipeline import render_pipeline
from ..tools.registry import ToolRegistry


def process_video(
    input_path: str,
    output_path: str,
    registry: ToolRegistry,
    analyzer: Analyzer,
    jobs: list[tuple[str, dict[str, Any]]],
    max_side: int = 1280,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"无法打开视频：{input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 1:
        fps = 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    ok, first = cap.read()
    if not ok:
        cap.release()
        raise ValueError("视频没有可读帧")

    h, w = first.shape[:2]
    if max_side and max(h, w) > max_side:
        scale = max_side / max(h, w)
        w, h = int(w * scale), int(h * scale)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
    if not writer.isOpened():
        cap.release()
        raise ValueError("无法创建输出视频（编码器不可用？）")

    index = 0
    frame = first
    try:
        while True:
            if frame.shape[1] != w or frame.shape[0] != h:
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
            out = render_pipeline(registry, analyzer, frame, jobs) if jobs else frame
            if out.shape[1] != w or out.shape[0] != h:
                out = cv2.resize(out, (w, h))
            writer.write(out)
            index += 1
            if on_progress is not None:
                on_progress(index, total)
            ok, frame = cap.read()
            if not ok:
                break
    finally:
        cap.release()
        writer.release()
    return index
