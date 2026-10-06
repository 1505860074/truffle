"""工具注册表：集中管理所有修饰工具，供大模型编排与执行器分发。"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseTool, ToolContext
from .enlarge_eyes import EnlargeEyesTool
from .remove_blemish import RemoveBlemishTool
from .skin_smooth import SkinSmoothTool
from .slim_face import SlimFaceTool
from .whiten import WhitenTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise KeyError(f"未知工具：{name}")
        return self._tools[name]

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def execute(
        self,
        name: str,
        image: np.ndarray,
        ctx: ToolContext,
        params: dict[str, Any],
    ) -> np.ndarray:
        tool = self.get(name)
        safe = tool.coerce_params(params)
        return tool.apply(image, ctx, **safe)


def build_default_registry() -> ToolRegistry:
    """内置工具集（MVP）。"""
    registry = ToolRegistry()
    for tool in (
        SkinSmoothTool(),
        WhitenTool(),
        SlimFaceTool(),
        EnlargeEyesTool(),
        RemoveBlemishTool(),
    ):
        registry.register(tool)
    return registry
