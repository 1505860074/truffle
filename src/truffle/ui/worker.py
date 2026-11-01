"""后台执行线程：把耗时的 LLM 调用与 CV 处理移出 UI 线程。"""

from __future__ import annotations

import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QThread, Signal

from ..agent.orchestrator import Orchestrator
from ..cv.analyzer import Analyzer
from ..tools.pipeline import render_pipeline
from ..tools.registry import ToolRegistry
from .i18n import tr


def friendly_error(exc: BaseException) -> str:
    """把常见的大模型/网络异常转成友好提示。"""
    name = type(exc).__name__
    text = str(exc)
    low = text.lower()
    if "Authentication" in name or "401" in text or "invalid_api_key" in low or "unauthorized" in low:
        return tr("API Key 无效或未授权，请在「设置」中检查。")
    if "RateLimit" in name or "429" in text or "insufficient" in low or "quota" in low:
        return tr("请求过于频繁或额度不足，请稍后再试。")
    if "Timeout" in name or "timed out" in low:
        return tr("请求超时，请检查网络或稍后重试。")
    if "Connection" in name or "Connect" in name or "getaddrinfo" in low:
        return tr("网络连接失败，请检查网络或接口地址。")
    if "model" in low and any(word in low for word in ("not found", "not exist", "does not exist", "invalid")):
        return tr("模型名称无效或不可用，请在设置中检查模型名称，并确认该模型支持工具调用（如 deepseek-chat）。")
    if "tool" in low and ("support" in low or "not" in low):
        return tr("当前模型可能不支持工具调用，请换用支持 function calling 的模型。")
    if "400" in text:
        return tr("请求被拒绝（400）。请检查模型名称、工具调用支持与请求参数。")
    return text or name


def _log_exception(exc: BaseException) -> None:
    try:
        base = Path(os.environ.get("APPDATA") or Path.home()) / "Truffle"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "error.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} [agent] =====\n")
            handle.write("".join(traceback.format_exception(exc)))
    except Exception:
        pass


class AgentWorker(QThread):
    imageReady = Signal()
    replied = Signal(str)
    failed = Signal(str)
    toolApplied = Signal(str, object)  # 工具名, 大模型实际使用的参数

    def __init__(
        self, orchestrator: Orchestrator, text: str,
        image: np.ndarray | None = None, context: str = "",
        history: list | None = None, manual: list | None = None, summary: str = "",
    ) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.text = text
        self.image = image
        self.context = context
        self.history = history
        self.manual = manual
        self.summary = summary

    def run(self) -> None:
        try:
            reply = self.orchestrator.handle(
                self.text,
                on_image=self.imageReady.emit,
                on_tool=self.toolApplied.emit,
                image=self.image,
                context=self.context,
                manual=self.manual,
                history=self.history,
                summary=self.summary,
            )
            self.replied.emit(reply)
        except Exception as exc:  # 线程内异常必须捕获后经信号回传
            _log_exception(exc)
            self.failed.emit(friendly_error(exc))


class VideoWorker(QThread):
    """视频修饰：逐帧套用工具管线并写出。"""

    progress = Signal(int, int)  # 已处理帧, 总帧
    failed = Signal(str)
    finished_ok = Signal(str)    # 输出路径

    def __init__(self, input_path, output_path, registry, analyzer, jobs, max_side) -> None:
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.registry = registry
        self.analyzer = analyzer
        self.jobs = jobs
        self.max_side = max_side

    def run(self) -> None:
        try:
            from ..core.video import process_video

            process_video(
                self.input_path, self.output_path, self.registry, self.analyzer,
                self.jobs, self.max_side, self.progress.emit,
            )
            self.finished_ok.emit(self.output_path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class BatchWorker(QThread):
    """批量风格匹配：对一组图片套用「向模板风格靠拢」的修正参数并导出。"""

    progress = Signal(int, int, str)  # 已完成, 总数, 输出路径
    failed = Signal(str)
    finished_ok = Signal(int)

    def __init__(self, registry, analyzer, template_profile, targets, out_dir, ext, quality,
                 mode: str = "template") -> None:
        super().__init__()
        self.registry = registry
        self.analyzer = analyzer
        self.template_profile = template_profile
        self.targets = targets
        self.out_dir = out_dir
        self.ext = ext
        self.quality = quality
        self.mode = mode

    def run(self) -> None:
        try:
            import os

            import cv2

            from ..core.score import auto_grade_jobs
            from ..core.style import match_params, profile

            done = 0
            total = len(self.targets)
            for path in self.targets:
                data = np.fromfile(path, dtype=np.uint8)
                image = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if image is None:
                    continue
                if self.mode == "auto":
                    jobs = auto_grade_jobs(image)
                else:
                    jobs = match_params(self.template_profile, profile(image))
                out = render_pipeline(self.registry, self.analyzer, image, jobs) if jobs else image
                name = os.path.splitext(os.path.basename(path))[0]
                out_path = os.path.join(self.out_dir, name + self.ext)
                params = []
                if self.ext in (".jpg", ".jpeg"):
                    params = [cv2.IMWRITE_JPEG_QUALITY, self.quality]
                ok, buf = cv2.imencode(self.ext, out, params)
                if ok:
                    buf.tofile(out_path)
                done += 1
                self.progress.emit(done, total, out_path)
            self.finished_ok.emit(done)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class PreviewWorker(QThread):
    """所见即所得：把「基图 + 当前所有非默认参数」渲染成预览图（后台线程）。"""

    previewReady = Signal(object)  # np.ndarray
    failed = Signal(str)

    def __init__(
        self,
        registry: ToolRegistry,
        jobs: list[tuple[str, dict[str, Any]]],
        base: np.ndarray,
        analyzer: Analyzer,
        mask: np.ndarray | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.jobs = jobs
        self.base = base
        self.analyzer = analyzer
        self.mask = mask

    def run(self) -> None:
        try:
            import cv2

            image = render_pipeline(self.registry, self.analyzer, self.base, self.jobs)
            if self.mask is not None:
                mask = self.mask
                if mask.shape[:2] != image.shape[:2]:
                    mask = cv2.resize(mask, (image.shape[1], image.shape[0]))
                alpha = (mask.astype(np.float32) / 255.0)[..., None]
                image = image.astype(np.float32) * alpha + self.base.astype(np.float32) * (1 - alpha)
                image = np.clip(image, 0, 255).astype(np.uint8)
            self.previewReady.emit(image)
        except Exception as exc:  # 线程内异常必须捕获后经信号回传
            self.failed.emit(str(exc))
