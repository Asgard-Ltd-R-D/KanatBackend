"""Checks for the Group statistics (SOW 2.1.3, #86). Hand-computable points only:
the arithmetic is verified independently of detection quality. No model, no video, no torch."""
import math

import numpy as np
import pytest

from detection import board
from detection.groups import groups
from detection.new_bullet_holes import _report


def _on(target, x, y):
    return {"target": target, "mm": (x, y)}


MISS = {"target": None, "mm": None}

# A 6 x 8 mm rectangle around (10, -5) plus its centre: every corner is a 3-4-5
# triangle away from the MPI, so the distances are 5, 5, 5, 5 and 0.
RECTANGLE = [_on(0, 13, -1), _on(0, 7, -1), _on(0, 13, -9), _on(0, 7, -9), _on(0, 10, -5)]


def test_a_hand_computable_group_gives_known_statistics():
    got, misses = groups(RECTANGLE)
    assert misses == 0
    g = got[0]
    assert g["n"] == 5
    assert g["mpi"] == pytest.approx((10.0, -5.0))
    assert g["cep"] == pytest.approx(5.0)                # median of 0, 5, 5, 5, 5
    assert g["mean_radius"] == pytest.approx(4.0)        # 20 / 5
    assert g["rms_radius"] == pytest.approx(math.sqrt(20.0))  # sqrt(100 / 5)
    assert g["extreme_spread"] == pytest.approx(10.0)    # the rectangle's diagonal


def test_a_3_4_5_triangle_gives_known_statistics():
    g = groups([_on(0, 0, 0), _on(0, 3, 0), _on(0, 0, 4)])[0][0]
    assert g["mpi"] == pytest.approx((1.0, 4 / 3))
    assert g["cep"] == pytest.approx(math.sqrt(52) / 3)  # distances sqrt(25, 52, 73) / 3
    assert g["mean_radius"] == pytest.approx((5 + math.sqrt(52) + math.sqrt(73)) / 9)
    assert g["rms_radius"] == pytest.approx(5 * math.sqrt(2) / 3)
    assert g["extreme_spread"] == pytest.approx(5.0)


def test_two_bullet_holes_give_every_measure():
    g = groups([_on(0, 0, 0), _on(0, 6, 8)])[0][0]
    assert g["mpi"] == pytest.approx((3.0, 4.0))
    assert g["cep"] == g["mean_radius"] == g["rms_radius"] == pytest.approx(5.0)
    assert g["extreme_spread"] == pytest.approx(10.0)


def test_one_bullet_hole_gives_an_mpi_and_no_spread():
    g = groups([_on(0, 2, -3)])[0][0]
    assert g["n"] == 1
    assert g["mpi"] == pytest.approx((2.0, -3.0))
    assert g["cep"] is g["mean_radius"] is g["rms_radius"] is g["extreme_spread"] is None


def test_misses_are_excluded_and_counted():
    got, misses = groups(RECTANGLE + [MISS, MISS])
    assert misses == 2
    assert got[0]["n"] == 5
    assert got[0]["mpi"] == pytest.approx((10.0, -5.0))


def test_two_targets_are_two_groups():
    got, _ = groups([_on(0, 0, 0), _on(1, 50, 50), _on(0, 6, 8)])
    assert got[0]["n"] == 2 and got[0]["mpi"] == pytest.approx((3.0, 4.0))
    assert got[1]["n"] == 1 and got[1]["mpi"] == pytest.approx((50.0, 50.0))


def test_a_target_without_new_bullet_holes_has_no_group():
    got, misses = groups([_on(1, 0, 0), MISS])
    assert list(got) == [1]
    assert groups([]) == ({}, 0)


# --- the report: one smoke check that the block appears ----------------------

def _square(x0, y0, side):
    return np.float32([[x0, y0], [x0 + side, y0], [x0 + side, y0 + side],
                       [x0, y0 + side]]).reshape(-1, 1, 2)


def _hole(target, pos):
    return {"target": target, "pos": np.float32(pos), "first_frame": 0,
            "persistence": 1.0, "corroborated": True, "seen": [0]}


def _run_report(mm_per_tpl_px, capsys, misses_only=False):
    view = board.BoardView(H=np.eye(3, dtype=np.float32), tpl_to_board=board._as_matrix(1.0),
                           canvas_size=(1000, 1000),
                           targets=[_square(0, 0, 100), _square(500, 500, 100)])
    new = [_hole(0, view.ring_centre(0)), _hole(0, view.ring_centre(0) + 10), _hole(None, (900, 50))]
    if misses_only:
        new = [_hole(None, (900, 50)), _hole(None, (50, 900))]
    _report(new, 0.0, 25.0, view, mm_per_tpl_px, [0])
    return capsys.readouterr().out


def test_the_report_prints_one_group_block_per_target_with_bullet_holes(capsys):
    out = _run_report(0.2, capsys)
    assert out.count("[GROUP] Target") == 1
    assert "[GROUP] Target 1: 2 Bullet Holes" in out
    assert "1 Miss excluded" in out
    assert "not Hits" in out


def test_without_a_print_scale_the_report_prints_no_group_block(capsys):
    out = _run_report(None, capsys)
    assert "[GROUP] Target" not in out
    assert "print scale is not configured" in out


def test_a_range_of_only_misses_still_reports_the_miss_count(capsys):
    out = _run_report(0.2, capsys, misses_only=True)
    assert "[GROUP] 2 Misses excluded from every Group" in out
    assert "[GROUP] Target" not in out
