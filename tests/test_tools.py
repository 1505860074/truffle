import numpy as np

from truffle.cv.analyzer import Analyzer
from truffle.tools.base import ToolContext
from truffle.tools.registry import build_default_registry


def _skin_image(size: int = 160) -> np.ndarray:
    img = np.zeros((size, size, 3), dtype=np.uint8)
    img[:] = (140, 160, 205)  # BGR，接近肤色
    noise = np.random.randint(-12, 12, img.shape, dtype=np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def test_registry_schemas_well_formed():
    registry = build_default_registry()
    schemas = registry.schemas()
    names = {s["function"]["name"] for s in schemas}
    assert "skin_smooth" in names
    assert "slim_face" in names
    for schema in schemas:
        assert schema["type"] == "function"
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


def test_coerce_clamps_out_of_range():
    tool = build_default_registry().get("skin_smooth")
    assert tool.coerce_params({"strength": 5})["strength"] == 1.0
    assert tool.coerce_params({"strength": -3})["strength"] == 0.0
    assert tool.coerce_params({})["strength"] == 0.5
    assert tool.coerce_params({"strength": "abc"})["strength"] == 0.5


def test_skin_smooth_modifies_skin():
    registry = build_default_registry()
    ctx = ToolContext(Analyzer())
    image = _skin_image()
    out = registry.execute("skin_smooth", image, ctx, {"strength": 0.8})
    assert out.shape == image.shape
    assert out.dtype == np.uint8
    assert not np.array_equal(out, image)


def test_zero_strength_is_noop():
    registry = build_default_registry()
    ctx = ToolContext(Analyzer())
    image = _skin_image()
    out = registry.execute("whiten", image, ctx, {"strength": 0.0})
    assert np.array_equal(out, image)


def test_every_registered_tool_runs_with_defaults():
    """参数栏里的每个工具（= AI 可调用 API）都能用默认参数跑通，不崩溃、形状不变。"""
    registry = build_default_registry()
    ctx = ToolContext(Analyzer())
    image = _skin_image(160)
    for tool in registry.all():
        params = {p.name: p.default for p in tool.parameters}
        out = registry.execute(tool.name, image, ctx, params)
        assert out.shape == image.shape, tool.name
        assert out.dtype == np.uint8, tool.name
