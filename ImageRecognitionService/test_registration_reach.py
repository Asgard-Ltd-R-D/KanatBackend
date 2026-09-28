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


def test_a_peak_on_the_search_window_edge_is_not_a_find():
    """Past SEARCH, the best score sits on the window's edge: a neighbour or
    the truncated slope of the mark, not the mark itself."""
    base = _spot(60, 60)
    patch = base[60 - rr.PATCH:60 + rr.PATCH + 1, 60 - rr.PATCH:60 + rr.PATCH + 1]
    assert rr.locate(_spot(60 + rr.SEARCH + 3, 60), patch, (60, 60))[0] is None


def test_a_search_window_off_the_frame_finds_nothing():
    base = _spot(60, 60)
    patch = base[50:71, 50:71]
    assert rr.locate(base, patch, (5, 60))[0] is None


def test_drift_is_what_holds_for_a_second_and_jitter_is_the_rest():
    t = np.arange(200)
    flicker = np.where(t % 2, 4.0, -4.0)                 # frame-to-frame, in x
    slide = np.linspace(0, 30, 200)                      # slow, in y
    d = np.stack([flicker, slide], axis=1)
    drift, jitter = rr.split(d)
    assert np.percentile(jitter, 95) == pytest.approx(4.0, abs=0.5)
    assert drift.max() == pytest.approx(30, abs=1.5)


def test_a_gap_in_the_samples_is_video_time_not_a_shorter_window():
    """A mark skipped for 100 frames between two steady positions: counting
    samples would average across the gap and call the step jitter."""
    frame = np.r_[0:100, 200:300]
    d = np.stack([np.where(frame < 100, 0.0, 10.0), np.zeros(200)], axis=1)
    assert rr.split(d, frame)[1].max() == pytest.approx(0)
    assert rr.split(d)[1].max() > 1                     # what the gap used to do


def test_cutting_marks_leaves_a_hole_round_each_and_the_rest_of_the_region():
    anchor = rr.board.Anchor(None, np.full((200, 200), 255, np.uint8), np.eye(3, dtype=np.float32))
    region = rr.cut_marks(anchor, [[100, 100]]).region
    assert region[100, 100] == 0 and region[100, 100 + rr.PATCH + rr.SEARCH + 1] == 255
    assert anchor.region[100, 100] == 255      # the runtime's own anchor is untouched
