"""The reach probe's tracker must find a mark where it is, or its error figures
are its own. No video."""
import types

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


def _scene(shift=(0.0, 0.0), size=(320, 240)):
    """Paper with a few dark blobs, the whole scene moved by `shift` px."""
    img = np.full(size[::-1], 200, np.float32)
    for x, y in [(60, 50), (250, 70), (120, 180), (200, 150), (40, 200)]:
        cv2.circle(img, (int(x * 4 + shift[0] * 4), int(y * 4 + shift[1] * 4)), 40, 40, -1,
                   shift=2)
    return cv2.GaussianBlur(img, (0, 0), 3)


@pytest.mark.parametrize("motion", [cv2.MOTION_AFFINE, cv2.MOTION_HOMOGRAPHY])
def test_the_anchoring_warp_takes_baseline_coordinates_onto_the_frame(motion):
    W = rr.ecc_warp(_scene(), _scene((5.0, -3.0)), motion, np.eye(3, dtype=np.float32))
    moved = rr.board._apply(W, [[100, 100]])[0]
    assert moved == pytest.approx([105, 97], abs=0.3)


def test_drift_is_what_holds_for_a_second_and_jitter_is_the_rest():
    t = np.arange(200)
    flicker = np.where(t % 2, 4.0, -4.0)                 # frame-to-frame, in x
    slide = np.linspace(0, 30, 200)                      # slow, in y
    d = np.stack([flicker, slide], axis=1)
    drift, jitter = rr.split(d)
    assert np.percentile(jitter, 95) == pytest.approx(4.0, abs=0.5)
    assert drift.max() == pytest.approx(30, abs=1.5)


def test_a_masked_warp_follows_the_scene_not_the_mask():
    """The region goes in as ECC's mask, not multiplied into both images,
    where its fixed edge would pull the warp towards no motion."""
    mask = np.zeros((240, 320), np.uint8)
    mask[20:220, 20:300] = 255
    W = rr.ecc_warp(_scene(), _scene((5.0, -3.0)), cv2.MOTION_HOMOGRAPHY,
                    np.eye(3, dtype=np.float32), mask)
    assert rr.board._apply(W, [[100, 100]])[0] == pytest.approx([105, 97], abs=0.3)


def test_the_texture_region_leaves_out_every_measured_mark():
    view = types.SimpleNamespace(H=np.eye(3, dtype=np.float32))
    ring = rr.board.RING_CENTRE_TPL
    mark = ring + [150, 0]
    region = rr.texture_region(view, (2000, 2000), 100, [mark])
    assert region[int(ring[1]), int(ring[0])] == 255
    assert region[int(mark[1]), int(mark[0])] == 0
    assert region[int(ring[1]), int(ring[0] + 200)] == 0   # past REGION_SPANS
