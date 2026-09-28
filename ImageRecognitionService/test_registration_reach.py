"""The reach probe's tracker must find a mark where it is, or its error figures
are its own. No video."""
import cv2
import numpy as np
import pytest

import registration_reach as rr


def _spot(cx, cy, size=120):
    """A blurred dark hole on paper, centred at a sub-pixel position."""
    img = np.full((size * 4, size * 4), 230, np.uint8)
    cv2.circle(img, (int(cx * 4), int(cy * 4)), 12, 40, -1)
    return cv2.resize(cv2.GaussianBlur(img, (0, 0), 6), (size, size),
                      interpolation=cv2.INTER_AREA)


@pytest.mark.parametrize("dx, dy", [(0.0, 0.0), (0.5, 0.0), (3.25, -2.5), (-7.0, 6.75)])
def test_a_mark_is_found_to_a_fraction_of_a_pixel(dx, dy):
    base = _spot(60, 60)
    patch = base[60 - rr.PATCH:60 + rr.PATCH + 1, 60 - rr.PATCH:60 + rr.PATCH + 1]
    found, score = rr.locate(_spot(60 + dx, 60 + dy), patch, (60, 60))
    assert score > 0.9
    assert found == pytest.approx([60 + dx, 60 + dy], abs=0.3)


def test_a_search_window_off_the_frame_finds_nothing():
    base = _spot(60, 60)
    patch = base[50:71, 50:71]
    assert rr.locate(base, patch, (5, 60))[0] is None
