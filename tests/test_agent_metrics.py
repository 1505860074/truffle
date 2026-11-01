from __future__ import annotations

import numpy as np

from truffle.agent.series import contact_sheet, export_batch, profile_with_consistency
from truffle.agent.solver import ParamSolver
from truffle.agent.style import PROFILES, resolve_style, style_distance
from truffle.cv.analyzer import Analyzer
from truffle.cv.metrics import STATE_SCHEMA, measure
from truffle.core.layer_doc import LayerDocument
from truffle.tools.registry import build_default_registry


def test_measure_schema_and_brightness() -> None:
    dark = np.full((48, 64, 3), 40, dtype=np.uint8)
    bright = np.full((48, 64, 3), 200, dtype=np.uint8)
    analyzer = Analyzer()
    dark_state = measure(dark, analyzer)
    bright_state = measure(bright, analyzer)
    assert dark_state["schema"] == STATE_SCHEMA
    assert bright_state["tone"]["ev"] > dark_state["tone"]["ev"]
    assert 0.0 <= dark_state["color"]["sat"] <= 1.0
    assert "style_vec" in dark_state


def test_style_resolve_and_distance() -> None:
    assert resolve_style("糖水").id == "tangshui"
    assert resolve_style("unknown", "natural").id == "natural"
    state = {
        "tone": {"contrast": 0.2, "ev": 0.3},
        "color": {"sat": 0.4, "skin_L": 0.7},
    }
    distance, deltas = style_distance(state, PROFILES["tangshui"])
    assert distance >= 0.0
    assert isinstance(deltas, dict)


def test_new_tools_registered_and_run() -> None:
    registry = build_default_registry()
    names = {tool.name for tool in registry.all()}
    assert {"exposure", "levels", "noise_reduction"} <= names
    image = np.full((64, 64, 3), 120, dtype=np.uint8)
    ctx_analyzer = Analyzer()
    from truffle.tools.base import ToolContext

    ctx = ToolContext(ctx_analyzer)
    out = registry.execute("exposure", image, ctx, {"ev": 0.5})
    assert out.shape == image.shape
    assert out.mean() > image.mean()


def test_solver_produces_jobs() -> None:
    registry = build_default_registry()
    analyzer = Analyzer()
    image = np.full((96, 128, 3), (80, 120, 180), dtype=np.uint8)
    solver = ParamSolver(registry, analyzer, preview_max=128, max_iterations=1, max_evaluations=4)
    result = solver.solve(image, PROFILES["tangshui"])
    assert result.before
    assert result.after
    assert 0.0 <= result.naturalness <= 1.0


def test_consistency_tightens_targets() -> None:
    profile = PROFILES["natural"]
    original = profile.all_targets()["color.skin_L"]
    adjusted = profile_with_consistency(
        profile, {"skin_L": 0.70, "contrast": 0.4, "sat": 0.3, "wb_k": 6000.0}, 1.0
    )
    tightened = adjusted.all_targets()["color.skin_L"]
    assert tightened[1] - tightened[0] < original[1] - original[0]
    assert tightened[0] <= 0.70 <= tightened[1]


def test_collapse_history_group() -> None:
    doc = LayerDocument()
    image = np.full((32, 32, 3), 100, dtype=np.uint8)
    doc.set_original(image)
    doc.add_layer("a")
    doc.add_layer("b")
    assert len(doc.steps()) == 2
    doc.collapse_recent(2, "AI 风格")
    assert len(doc.steps()) == 1
    assert doc.steps()[0].kind == "group"
    assert doc.can_undo
    assert doc.undo()
    assert len(doc.layers()) == 1


def test_contact_sheet_and_export(tmp_path) -> None:
    images = [np.full((40, 60, 3), 90, dtype=np.uint8) for _ in range(5)]
    sheet = contact_sheet(images, columns=3, cell=50)
    assert sheet.shape == (100, 150, 3)
    paths = export_batch(images, tmp_path, long_side=40)
    assert len(paths) == 5
    assert all(path.exists() for path in paths)
