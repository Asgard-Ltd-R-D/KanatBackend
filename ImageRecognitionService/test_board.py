"""Checks for Board geometry. No model, no video, no torch."""
import numpy as np
import pytest

import board


def _square(x0, y0, side):
    return np.float32([[x0, y0], [x0 + side, y0], [x0 + side, y0 + side],
                       [x0, y0 + side]]).reshape(-1, 1, 2)


def _view(targets, scale=1.0):
    """A BoardView with Board space already fixed — no registration needed."""
    return board.BoardView(H=np.eye(3, dtype=np.float32),
                           tpl_to_board=board._as_matrix(scale),
                           canvas_size=(1000, 1000),
                           targets=targets)


# --- net scale: the rule that decides whether the detector sees anything ----

def test_net_scale_is_the_product_of_both_scalings():
    """imgsz alone says nothing; the warp has already moved the scale."""
    assert board.net_scale(board_scale=2.0, template_span_px=100,
                           frame_span_px=200, imgsz=500,
                           canvas_long_side=1000) == pytest.approx(0.5)


def test_net_scale_measures_against_the_longest_side():
    """ultralytics fits the longest side, so a portrait canvas must not use width.

    A 709x1063 Board at imgsz 704 is a 0.66 letterbox, not 0.99. Reading it off
    the width overstates net scale by half and quietly starves the detector.
    """
    portrait = board.net_scale(1.0, 100, 100, imgsz=704, canvas_long_side=1063)
    assert portrait == pytest.approx(704 / 1063, abs=1e-6)


def test_measured_zero_detection_configurations_share_one_net_scale():
    """The three canvas sizes that measured zero detections are all net ~1.81.

    An octave apart in resolution, identical in net scale, identical in outcome.
    This is the evidence that net scale governs and resolution does not, so it is
    pinned rather than left in prose.
    """
    foot, tpl = 564.0, 1049.0
    # these canvases are landscape, so width is also the longest side
    got = [board.net_scale(size / tpl, tpl, foot, 1280, width)
           for size, width in ((1120, 1405), (1600, 2007), (2400, 3010))]
    assert got == pytest.approx([1.81, 1.81, 1.81], abs=0.02)


def test_board_scale_lands_on_the_requested_net_scale():
    """Round-trip: ask for 0.9, and a full-canvas inference gets 0.9."""
    tpl_span, frame_span = 1049.0, 564.0
    k = board.board_scale_for(tpl_span, frame_span, wanted=0.90)
    canvas_long = k * tpl_span
    assert board.net_scale(k, tpl_span, frame_span, imgsz=canvas_long,
                           canvas_long_side=canvas_long) == pytest.approx(0.90)


# --- Target assignment and Miss ---------------------------------------------

def test_bullet_hole_inside_a_target_is_assigned_to_it():
    view = _view([_square(0, 0, 100), _square(500, 500, 100)])
    assert view.assign((50, 50)) == 0
    assert view.assign((550, 550)) == 1


def test_bullet_hole_outside_every_target_is_a_miss():
    """A real Hit on the Board, counted, but carrying no score."""
    view = _view([_square(0, 0, 100), _square(500, 500, 100)])
    assert view.assign((300, 300)) is None


def test_miss_is_not_claimed_by_the_nearest_target():
    """Just outside a Target is still a Miss — proximity does not score."""
    view = _view([_square(0, 0, 100)])
    assert view.assign((101, 50)) is None


def test_board_with_no_targets_assigns_nothing():
    assert _view([]).assign((10, 10)) is None


# --- calibration is blocked, and says so ------------------------------------

def test_millimetres_refuses_to_guess_the_ring_diameter():
    """Everything downstream scales linearly with it, so it must not default."""
    with pytest.raises(board.NotCalibrated, match="has not been measured"):
        board.to_millimetres([[0, 0]], _view([]))


def test_scoring_is_blocked_on_the_same_measurement():
    with pytest.raises(board.NotCalibrated):
        board.score([[0, 0]], _view([]), ring_diameter_mm=42.6)


def test_millimetres_work_once_the_ring_is_measured():
    """A Bullet Hole one ring-radius right of centre is half a diameter right."""
    view = _view([], scale=1.0)
    centre = board.RING_CENTRE_TPL
    offset = centre + np.array([board.RING_DIAMETER_TPL / 2, 0])
    mm = board.to_millimetres([centre, offset], view, ring_diameter_mm=40.0)
    assert mm[0] == pytest.approx([0.0, 0.0])
    assert mm[1] == pytest.approx([20.0, 0.0])


def test_millimetres_are_independent_of_board_scale():
    """Rectifying larger must not change a physical measurement."""
    centre = board.RING_CENTRE_TPL
    offset = centre + np.array([board.RING_DIAMETER_TPL / 2, 0])
    at_one = board.to_millimetres([offset], _view([], scale=1.0), ring_diameter_mm=40.0)
    at_three = board.to_millimetres([offset * 3], _view([], scale=3.0), ring_diameter_mm=40.0)
    # abs, not relative: one component is zero, and float32 leaves ~1e-5 mm of
    # noise there. A micron is five thousand times under SOW 2.3.2's budget.
    assert at_one[0] == pytest.approx(at_three[0], abs=1e-3)


def test_physical_y_grows_upward():
    """Image y grows down; a Bullet Hole above centre must read positive."""
    view = _view([])
    above = board.RING_CENTRE_TPL - np.array([0, board.RING_DIAMETER_TPL / 2])
    assert board.to_millimetres([above], view, ring_diameter_mm=40.0)[0][1] == pytest.approx(20.0)
