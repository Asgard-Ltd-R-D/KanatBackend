"""Checks for #272's regression rule and the canvas-shift control. No model, no video."""
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
            "fp_before_change_filter": 0, "device": "cpu"}


def _result(*shifts, stride=1, window=(13, 25), sha256="v", truth_sha256="t"):
    return {"stride": stride, "recordings": {"rec": {
        "window": list(window), "sha256": sha256, "truth_sha256": truth_sha256,
        "shifts": {str(d): s for d, s in zip((0, 8, 16, 32), shifts)}}}}


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
    assert _kinds(REF, _result(_shift([_tp(1, 2.1, 1.0), _tp(2)]))) == (
        [("moved", "truth #1", False, True)], False)
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


def test_results_in_template_px_are_not_ruled_on():
    px = _shift([_tp(1), _tp(2)])
    px["unit"] = "template px"
    assert _kinds(REF, _result(px)) == ([("not comparable", "-", False, True)], False)


def test_a_shifted_miss_does_not_excuse_a_move_or_the_limit():
    ref = _result(_shift([_tp(1, 4.5, 0.0)]), _shift([_fn(1)]))
    assert _kinds(ref, _result(_shift([_tp(1, 5.6, 0.0)]))) == (
        [("moved", "truth #1", False, True), ("over limit", "truth #1", False, True)], False)


def test_a_shifted_move_over_the_bound_is_noise():
    ref = _result(_shift([_tp(1)]), _shift([_tp(1, 2.5, 1.0)]))
    assert _kinds(ref, _result(_shift([_tp(1, 2.1, 1.0)]))) == (
        [("moved", "truth #1", True, False)], True)


def test_results_from_other_settings_are_not_ruled_on():
    mps = _shift([_tp(1), _tp(2)])
    mps["device"] = "mps"
    for new in (_result(STEADY, stride=17), _result(STEADY, window=(13, 20)), _result(mps)):
        assert _kinds(REF, new) == ([("not comparable", "-", False, True)], False)


def test_results_on_other_bytes_or_truth_are_not_ruled_on():
    for new in (_result(STEADY, sha256="w"), _result(STEADY, truth_sha256="u"),
                _result(STEADY, sha256=None)):
        assert _kinds(REF, new) == ([("not comparable", "-", False, True)], False)


def test_the_truth_hash_reads_labels_but_not_arrivals(tmp_path):
    (tmp_path / "board.new.txt").write_text("0 0.5 0.5\n")
    before = regression.truth_hash(tmp_path)
    (tmp_path / regression.ARRIVAL_NAME).write_text("120\n")
    assert regression.truth_hash(tmp_path) == before
    (tmp_path / "board.new.txt").write_text("0 0.5 0.6\n")
    assert regression.truth_hash(tmp_path) != before
