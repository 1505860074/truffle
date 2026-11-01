"""工具注册表：集中管理所有修饰工具，供大模型编排与执行器分发。"""

from __future__ import annotations

from typing import Any

import numpy as np

from .background_blur import BackgroundBlurTool
from .base import BaseTool, ToolContext
from .body_slim import BodySlimTool
from .color_adjust import ColorAdjustTool
from .color_temp import ColorTempTool
from .curves import CurvesTool
from .dehaze import DehazeTool
from .distort import DistortTool
from .enlarge_eyes import EnlargeEyesTool
from .exposure import ExposureTool
from .levels import LevelsTool
from .noise_reduction import NoiseReductionTool
from .eye_brighten import EyeBrightenTool
from .film import FilmTool
from .hair_color import HairColorTool
from .hdr import HdrTool
from .hsl import HslTool
from .leg_lengthen import LegLengthenTool
from .lipstick import LipstickTool
from .remove_blemish import RemoveBlemishTool
from .remove_dark_circles import RemoveDarkCirclesTool
from .rotate_flip import RotateFlipTool
from .sharpen_clarity import SharpenClarityTool
from .skin_smooth import SkinSmoothTool
from .slim_face import SlimFaceTool
from .teeth_whiten import TeethWhitenTool
from .tone_recovery import ToneRecoveryTool
from .vignette import VignetteTool
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
    """内置工具集：人像修饰 + 基础调色 + 形变 + 局部精修。"""
    registry = ToolRegistry()
    for tool in (
        # 调色 / 影调
        ExposureTool(),
        LevelsTool(),
        ColorAdjustTool(),
        ColorTempTool(),
        NoiseReductionTool(),
        HslTool(),
        CurvesTool(),
        ToneRecoveryTool(),
        DehazeTool(),
        HdrTool(),
        SharpenClarityTool(),
        VignetteTool(),
        FilmTool(),
        # 构图
        RotateFlipTool(),
        # 人像
        SkinSmoothTool(),
        WhitenTool(),
        SlimFaceTool(),
        EnlargeEyesTool(),
        RemoveBlemishTool(),
        TeethWhitenTool(),
        RemoveDarkCirclesTool(),
        EyeBrightenTool(),
        HairColorTool(),
        LipstickTool(),
        BackgroundBlurTool(),
        # 形体 / 形变
        BodySlimTool(),
        LegLengthenTool(),
        DistortTool(),
    ):
        registry.register(tool)
    return registry
