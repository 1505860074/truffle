import numpy as np

from truffle.core.layers import Layer, LayerStack, ensure_bgra


def _layer(value: int, alpha: int = 255, **kwargs) -> Layer:
    img = np.zeros((20, 20, 4), dtype=np.uint8)
    img[..., :3] = value
    img[..., 3] = alpha
    return Layer(id=1, name="L", image=img, **kwargs)


def test_composite_normal_and_opacity():
    stack = LayerStack()
    stack.add_layer(_layer(100))
    stack.add_layer(_layer(200, opacity=0.5))
    out = stack.composite()
    assert np.allclose(out[0, 0], 150, atol=2)


def test_composite_hidden_and_mask():
    stack = LayerStack()
    stack.add_layer(_layer(50))
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[:, :10] = 255
    stack.add_layer(_layer(250, mask=mask))
    out = stack.composite()
    assert out[0, 0, 0] == 250
    assert out[0, 19, 0] == 50

    stack.set_active(1)
    stack.layers[1] = _layer(250, mask=mask, visible=False)
    out = stack.composite()
    assert out[0, 0, 0] == 50


def test_blend_modes():
    stack = LayerStack()
    stack.add_layer(_layer(100))
    stack.add_layer(_layer(200, blend="multiply"))
    out = stack.composite()
    assert np.allclose(out[0, 0, 0], 100 * 200 / 255, atol=2)

    stack.layers[1] = _layer(200, blend="difference")
    out = stack.composite()
    assert np.allclose(out[0, 0, 0], 100, atol=2)


def test_merge_down_and_flatten():
    stack = LayerStack()
    stack.add_layer(_layer(30))
    stack.add_layer(_layer(60, alpha=128))
    assert stack.merge_down(1)
    assert len(stack.layers) == 1
    merged = stack.composite()
    assert merged[0, 0, 0] > 30

    stack.add_layer(_layer(90))
    flat = stack.flatten()
    assert flat.shape == (20, 20, 3)


def test_crop_and_resize_canvas():
    stack = LayerStack()
    stack.add_layer(_layer(77))
    stack.crop(2, 3, 10, 8)
    assert stack.size() == (10, 8)
    assert stack.composite()[0, 0, 0] == 77

    stack.resize_canvas(30, 30, (5, 5))
    out = stack.composite()
    assert stack.size() == (30, 30)
    assert out[5, 5, 0] == 77
    assert out[0, 0, 0] == 255


def test_ensure_bgra_converts():
    bgr = np.full((4, 4, 3), 10, np.uint8)
    out = ensure_bgra(bgr)
    assert out.shape == (4, 4, 4)
    assert out[0, 0, 3] == 255
