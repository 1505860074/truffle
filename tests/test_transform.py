import numpy as np

from truffle.core.selection import rect_mask
from truffle.core.transform import (
    flip_quad, homography, quad_from_rect, rotate_quad, transform_layer,
    translate_quad,
)


def _image() -> np.ndarray:
    img = np.zeros((40, 40, 4), np.uint8)
    img[..., 3] = 255
    img[5:25, 5:25, :3] = (10, 20, 30)
    return img


def test_quad_helpers_and_homography():
    quad = quad_from_rect((0, 0, 10, 10))
    moved = translate_quad(quad, 5, 6)
    assert moved[0] == (5.0, 6.0)
    h = homography(quad, moved)
    assert h.shape == (3, 3)

    flipped = flip_quad(quad, horizontal=True, vertical=False)
    assert flipped[0][0] == 10.0
    assert flipped[1][0] == 0.0

    rotated = rotate_quad(quad, 90)
    assert len(rotated) == 4


def test_transform_whole_layer_moves_pixels():
    img = _image()
    out = transform_layer(img, (0, 0, 40, 40), quad_from_rect((5, 5, 40, 40)))
    assert out.shape == img.shape
    assert out[10, 10, 0] == 10
    assert out[0, 0, 3] == 0


def test_transform_selection_only_changes_inside():
    img = _image()
    sel = rect_mask((40, 40), 5, 5, 20, 20)
    out = transform_layer(img, (5, 5, 20, 20), quad_from_rect((10, 10, 20, 20)), sel)
    assert out[0, 0, 3] == 255
    assert out[35, 35, 3] == 255
    assert out[10, 10, 0] == 10
    assert out[5, 5, 3] == 0
