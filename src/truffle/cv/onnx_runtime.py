"""ONNX Runtime 统一入口：CUDA → DirectML → CPU 自动回退。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_PROVIDER_ORDER = (
    "CUDAExecutionProvider",
    "DmlExecutionProvider",
    "CPUExecutionProvider",
)


def available_providers() -> list[str]:
    try:
        import onnxruntime as ort

        return list(ort.get_available_providers())
    except Exception:
        return []


def preferred_providers() -> list[str]:
    available = set(available_providers())
    return [name for name in _PROVIDER_ORDER if name in available]


def load_session(model_path: str | Path) -> Any | None:
    path = Path(model_path)
    if not path.exists():
        return None
    try:
        import onnxruntime as ort

        providers = preferred_providers()
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        return ort.InferenceSession(str(path), sess_options=options, providers=providers or None)
    except Exception:
        return None


def provider_of(session: Any | None) -> str:
    if session is None:
        return "none"
    try:
        return str(session.get_providers()[0])
    except Exception:
        return "unknown"


def backend_name() -> str:
    providers = preferred_providers()
    if "CUDAExecutionProvider" in providers:
        return "onnx-cuda"
    if "DmlExecutionProvider" in providers:
        return "onnx-directml"
    if "CPUExecutionProvider" in providers:
        return "onnx-cpu"
    return "heuristic"
