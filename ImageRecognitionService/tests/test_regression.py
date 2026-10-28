import numpy as np

from detection import board
from tools import regression


def _tp(j, dx=1.0, dy=1.0):
    return {"truth": j, "outcome": "TP", "dx": dx, "dy": dy}


def _fn(j):
    return {"truth": j, "outcome": "FN", "dx": None, "dy": None}


def _fp(x, y):
    return {"found": 9, "x": x, "y": y}


def _shift(truth, fps=()):
    return {"truth": truth, "false_positives": list(fps), "unit": "mm",
            "fp_before_change_filter": 0}


def _result(*shifts):
    return {"recordings": {"rec": {"shifts": {str(d): s for d, s in zip((0, 8, 16, 32), shifts)}}}}


def _kinds(ref, new):
    findings, passed = regression.compare(ref, new)
    return [(f["kind"], f["hole"], f["noise"], f["fails"]) for f in findings], passed


STEADY = _shift([_tp(1), _tp(2)])
REF = _result(STEADY, STEADY, STEADY, STEADY)


def test_an_unchanged_result_passes():
    assert _kinds(REF, _result(STEADY)) == ([], True)


def test_a_lost_hole_fails():
    assert _kinds(REF, _result(_shift([_tp(1), _fn(2)]))) == (
        [("lost", "truth #2", False, True)], False)


def test_an_added_false_positive_fails():
    assert _kinds(REF, _result(_shift([_tp(1), _tp(2)], [_fp(500, 500)]))) == (
        [("added", "FP found #9", False, True)], False)


def test_a_hole_moved_over_1_mm_fails_and_under_passes():
    assert _kinds(REF, _result(_shift([_tp(1, 2.1, 1.0), _tp(2)])))[1] is False
    assert _kinds(REF, _result(_shift([_tp(1, 1.9, 1.0), _tp(2)]))) == ([], True)


def test_a_hole_at_5_mm_fails():
    ref = _result(*[_shift([_tp(1, 4.5, 0.0)])] * 4)
    assert _kinds(ref, _result(_shift([_tp(1, 5.0, 0.0)]))) == (
        [("over limit", "truth #1", False, True)], False)


def test_a_failure_the_control_shows_is_noise():
    flips = _result(STEADY, STEADY, _shift([_tp(1), _fn(2)], [_fp(510, 495)]), STEADY)
    kinds, passed = _kinds(flips, _result(_shift([_tp(1), _fn(2)], [_fp(500, 500)])))
    assert kinds == [("lost", "truth #2", True, False), ("added", "FP found #9", True, False)]
    assert passed


def test_the_canvas_shift_moves_the_canvas_not_the_positions():
    tpl_to_board = board._as_matrix(0.2, (-10.0, -20.0))
    view = board.BoardView(np.eye(3), tpl_to_board, (300, 200),
                           [np.float32([[[50, 60]]])], edges={"above": 5.0})
    moved = board.shifted(view, 8)
    assert np.allclose(moved.template_to_board([[100, 100]]),
                       view.template_to_board([[100, 100]]) - 8)
    assert np.allclose(moved.board_to_template(moved.template_to_board([[100, 100]])),
                       [[100, 100]])
    assert moved.targets[0].tolist() == [[[42, 52]]]
    assert moved.edges["above"] == -3.0
    assert moved.canvas_size == view.canvas_size
