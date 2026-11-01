import numpy as np

from truffle.core.layer_doc import LayerDocument
from truffle.core.selection import rect_mask
from truffle.core.transform import quad_from_rect


def _doc() -> LayerDocument:
    doc = LayerDocument()
    doc.set_original(np.full((30, 40, 3), 100, np.uint8))
    return doc


def test_load_and_composite():
    doc = _doc()
    assert doc.is_loaded
    assert len(doc.layers()) == 1
    assert doc.current.shape == (30, 40, 3)
    assert np.all(doc.current == 100)


def test_layer_add_duplicate_delete_and_undo():
    doc = _doc()
    doc.add_layer("A")
    assert len(doc.layers()) == 2
    doc.duplicate_active_layer()
    assert len(doc.layers()) == 3
    doc.delete_active_layer()
    assert len(doc.layers()) == 2
    assert doc.can_undo
    doc.undo()
    assert len(doc.layers()) == 3
    doc.redo()
    assert len(doc.layers()) == 2


def test_tool_push_and_history_edit():
    doc = _doc()

    def render(image, step):
        return np.clip(image.astype(np.int16) + step.data.get("add", 0), 0, 255).astype(np.uint8)

    doc.set_renderer(render)
    doc.push_op("tool", "t", {"name": "t", "params": {}, "add": 20})
    assert doc.current[0, 0, 0] == 120
    doc.push_op("tool", "t", {"name": "t", "params": {}, "add": 30})
    assert doc.current[0, 0, 0] == 150

    doc.update_step(0, {"name": "t", "params": {}, "add": 5})
    assert len(doc.steps()) == 1
    assert doc.current[0, 0, 0] == 105


def test_transform_and_mask():
    doc = _doc()
    top = np.full((30, 40, 4), 200, np.uint8)
    top[..., 3] = 255
    doc.add_layer("top", image=top)
    doc.transform_active((0, 0, 40, 30), quad_from_rect((5, 5, 40, 30)), None)
    out = doc.current
    assert out[0, 0, 0] == 100
    assert out[10, 10, 0] == 200

    mask = rect_mask((30, 40), 0, 0, 10, 10)
    doc.add_mask_from_selection(mask)
    assert doc.active_layer.mask is not None
    doc.delete_mask()
    assert doc.active_layer.mask is None


def test_layer_via_copy_keeps_only_selection():
    doc = _doc()
    doc.add_layer("top", image=np.dstack([
        np.full((30, 40, 3), 200, np.uint8), np.full((30, 40), 255, np.uint8)
    ]))
    mask = rect_mask((30, 40), 0, 0, 10, 10)
    doc.layer_via_copy(mask)
    new = doc.active_layer
    assert new is not None
    assert new.image[5, 5, 3] == 255
    assert new.image[20, 20, 3] == 0


def test_crop_changes_canvas_all_layers():
    doc = _doc()
    top = np.full((30, 40, 4), 200, np.uint8)
    top[..., 3] = 255
    doc.add_layer("top", image=top)
    doc.push_op("crop", "裁剪", {"rect": (5, 5, 20, 10)})
    assert doc.current.shape == (10, 20, 3)
    assert len(doc.layers()) == 2


def test_rotate_flip_keeps_layers():
    doc = _doc()
    top = np.full((30, 40, 4), 200, np.uint8)
    top[..., 3] = 255
    doc.add_layer("top", image=top)
    doc.commit_tool("rotate_flip", {"rotate": 90, "flip": "none"}, top[..., :3])
    assert len(doc.layers()) == 2
    assert doc.current.shape == (40, 30, 3)


def test_reset_restores_original():
    doc = _doc()
    doc.add_layer("A")
    doc.reset()
    assert doc.pointer() == 0
    assert len(doc.layers()) == 1
    assert np.all(doc.current == 100)
