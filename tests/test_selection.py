import cv2
import numpy as np

from truffle.core.selection import (
    bounds, combine, contours, ellipse_mask, feather_mask, invert, is_empty,
    polygon_mask, rect_mask, wand_mask,
)


def test_rect_and_ellipse_bounds():
    rect = rect_mask((50, 60), 10, 12, 20, 18)
    assert bounds(rect) == (10, 12, 20, 18)
    assert rect[20, 15] == 255
    assert rect[0, 0] == 0

    ellipse = ellipse_mask((50, 60), 10, 12, 20, 18)
    assert bounds(ellipse) is not None
    assert ellipse[20, 20] == 255
    assert ellipse[12, 10] == 0


def test_polygon_and_combine():
    poly = polygon_mask((50, 60), [(5, 5), (40, 5), (40, 40)])
    assert poly[10, 10] == 255
    assert poly[45, 55] == 0

    extra = rect_mask((50, 60), 30, 30, 10, 10)
    added = combine(poly, extra, "add")
    assert added[35, 35] == 255
    sub = combine(added, extra, "subtract")
    assert sub[35, 35] == 0
    inter = combine(poly, rect_mask((50, 60), 0, 0, 10, 10), "intersect")
    assert inter[7, 7] == 255


def test_wand_contiguous_and_global():
    img = np.zeros((40, 40, 3), np.uint8)
    cv2.rectangle(img, (5, 5), (20, 20), (200, 50, 50), -1)
    cv2.rectangle(img, (30, 30), (35, 35), (200, 50, 50), -1)

    contiguous = wand_mask(img, 10, 10, tolerance=10, contiguous=True)
    assert contiguous[10, 10] == 255
    assert contiguous[32, 32] == 0

    global_mask = wand_mask(img, 10, 10, tolerance=10, contiguous=False)
    assert global_mask[32, 32] == 255


def test_feather_invert_contours():
    mask = rect_mask((50, 60), 10, 10, 20, 20)
    feathered = feather_mask(mask, 4)
    assert feathered.dtype == np.uint8
    assert feathered[20, 20] > 0
    assert feathered[0, 0] == 0

    inv = invert(mask)
    assert inv[20, 20] == 0
    assert inv[0, 0] == 255

    assert contours(mask)
    assert is_empty(np.zeros((5, 5), np.uint8))
