"""工具基类与执行上下文。

每个修饰能力 = 一个 `BaseTool` 子类。工具同时向两方暴露自己：
- 给大模型看的 JSON Schema（`schema()`）；
- 给执行器用的 `apply()`。
一份定义两处共用，新增工具无需改动编排逻辑。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..cv.analyzer import Analysis, Analyzer


@dataclass
class ToolParameter:
    name: str
    description: str
    type: str = "number"  # number | integer | boolean | string
    minimum: float | None = None
    maximum: float | None = None
    default: Any = None
    enum: list[Any] | None = None

    def to_schema(self) -> dict:
        schema: dict[str, Any] = {"type": self.type, "description": self.description}
        if self.type in ("number", "integer"):
            if self.minimum is not None:
                schema["minimum"] = self.minimum
            if self.maximum is not None:
                schema["maximum"] = self.maximum
        if self.enum:
            schema["enum"] = self.enum
        return schema


class ToolContext:
    """一次对话轮次内的共享上下文，缓存图像分析结果避免重复检测。"""

    def __init__(self, analyzer: Analyzer) -> None:
        self.analyzer = analyzer

    def analyze(self, image: np.ndarray) -> Analysis:
        return self.analyzer.analyze(image)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: list[ToolParameter] = []

    def schema(self) -> dict:
        properties = {p.name: p.to_schema() for p in self.parameters}
        required = [p.name for p in self.parameters if p.default is None]
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def coerce_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """校验并夹紧参数：填默认值、类型转换、范围限制。

        大模型可能给出非法参数，这里统一兜底，避免工具内部崩溃。
        """
        out: dict[str, Any] = {}
        for p in self.parameters:
            value = params.get(p.name, p.default)
            if value is None:
                out[p.name] = p.default
                continue
            if p.type in ("number", "integer"):
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    value = p.default if p.default is not None else 0.0
                if p.type == "integer":
                    value = int(round(value))
                if p.minimum is not None:
                    value = max(p.minimum, value)
                if p.maximum is not None:
                    value = min(p.maximum, value)
            elif p.type == "boolean":
                value = bool(value)
            elif p.enum and value not in p.enum:
                value = p.default
            out[p.name] = value
        return out

    @abstractmethod
    def apply(
        self, image: np.ndarray, ctx: ToolContext, **params: Any
    ) -> np.ndarray:
        """返回修饰后的新图像（不要原地修改入参）。"""
        raise NotImplementedError
