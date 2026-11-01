import numpy as np

from truffle.core.image_doc import ImageDocument


def _img(value: int = 100) -> np.ndarray:
    return np.full((10, 10, 3), value, dtype=np.uint8)


def test_load_save_roundtrip(tmp_path):
    import cv2

    doc = ImageDocument()
    path = tmp_path / "in.png"
    cv2.imwrite(str(path), _img(50))
    doc.load(path)
    assert doc.is_loaded

    out = tmp_path / "out.png"
    doc.save(out)
    assert out.exists()


def test_undo_redo():
    doc = ImageDocument()
    doc.set_original(_img(10))

    doc.push(_img(20))
    doc.push(_img(30))
    assert doc.current[0, 0, 0] == 30
    assert doc.can_undo

    doc.undo()
    assert doc.current[0, 0, 0] == 20
    doc.undo()
    assert doc.current[0, 0, 0] == 10
    assert not doc.can_undo

    doc.redo()
    assert doc.current[0, 0, 0] == 20


def test_reset_to_original():
    doc = ImageDocument()
    doc.set_original(_img(10))
    doc.push(_img(99))
    doc.reset()
    assert doc.current[0, 0, 0] == 10


def test_replayable_step_and_edit():
    from truffle.core.image_doc import Step

    doc = ImageDocument()
    doc.set_original(_img(10))

    # 可重放步骤：renderer 负责实际渲染（测试里用 +10 代替工具）
    def render(image, step):
        return np.clip(image.astype(np.int16) + step.data["add"], 0, 255).astype(np.uint8)

    doc.set_renderer(render)
    doc.push_op("tool", "t", {"add": 20})
    doc.push_op("tool", "t", {"add": 30})
    assert doc.current[0, 0, 0] == 60

    # 修改第 0 步参数后，后续自动重算
    doc.update_step(0, {"add": 5})
    assert doc.current[0, 0, 0] == 45

    # 删除第 0 步后重算
    doc.delete_step(0)
    assert doc.current[0, 0, 0] == 40
