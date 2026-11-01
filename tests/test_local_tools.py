from __future__ import annotations

import numpy as np

from truffle.core.masks import linear_mask, mask_from_params, rect_mask
from truffle.cv.analyzer import Analyzer
from truffle.tools.base import ToolContext
from truffle.tools.registry import build_default_registry


def test_masks_geometry() -> None:
    rect = rect_mask(40, 60, 0.1, 0.1, 0.5, 0.5, 0.0)
    assert rect.shape == (40, 60)
    assert rect[10, 10] == 255
    assert rect[35, 55] == 0
    linear = linear_mask(40, 60, 0.0, 0.0, 1.0, 0.0, 0.2)
    assert linear[20, 0] < linear[20, 59]
    radial = mask_from_params(40, 60, {"shape": "radial", "x1": 0.5, "y1": 0.5, "x2": 0.9, "y2": 0.9})
    assert radial[20, 30] > radial[0, 0]


def test_local_tools_registered_and_run() -> None:
    registry = build_default_registry()
    names = {tool.name for tool in registry.all()}
    assert {"local_adjust", "dodge_burn", "clone", "face_light", "iris", "hair_enhance"} <= names
    image = np.full((80, 100, 3), 110, dtype=np.uint8)
    ctx = ToolContext(Analyzer())
    for name in ("local_adjust", "dodge_burn", "clone", "face_light", "iris", "hair_enhance"):
        tool = registry.get(name)
        out = registry.execute(name, image, ctx, {p.name: p.default for p in tool.parameters})
        assert out.shape == image.shape
        assert out.dtype == np.uint8


def test_local_adjust_changes_mask_region() -> None:
    registry = build_default_registry()
    image = np.full((80, 100, 3), 100, dtype=np.uint8)
    out = registry.execute(
        "local_adjust", image, ToolContext(Analyzer()),
        {"shape": "rect", "x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4,
         "feather": 0.0, "exposure": 1.0, "brightness": 0.0,
         "contrast": 0.0, "saturation": 0.0},
    )
    assert out[16, 20].mean() > image[16, 20].mean()
    assert np.array_equal(out[70, 90], image[70, 90])


def test_clone_copies_patch() -> None:
    registry = build_default_registry()
    image = np.zeros((80, 100, 3), dtype=np.uint8)
    image[23:37, 23:37] = 200
    out = registry.execute(
        "clone", image, ToolContext(Analyzer()),
        {"src_x": 0.3, "src_y": 0.3, "dst_x": 0.7, "dst_y": 0.7,
         "radius": 0.08, "feather": 0.0, "opacity": 1.0},
    )
    assert out[56, 70].mean() > 50
