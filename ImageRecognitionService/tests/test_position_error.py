"""Checks for the pooled stage-1 Position Error report. No model, no video."""
import numpy as np
import pytest

from tools.position_error import select, summarise

# (dX, dY, radial) mm, as `evaluate.position_errors` gives them. The third sits
# exactly on 5 mm in X.
ROWS = [[3.0, -4.0, 5.0],
        [-1.2, 1.6, 2.0],
        [5.0, 0.0, 5.0],
        [0.0, -2.0, 2.0]]


def test_the_summary_on_hand_computed_rows():
    s = summarise(ROWS, [True, False, False, True])
    assert s["n"] == 4 and s["on_target"] == 2
    assert s["bias"] == pytest.approx([1.7, -1.1])
    # P95 interpolates between the order statistics: rank 0.95 x 3 = 2.85.
    assert s["dx"] == pytest.approx({"mean": 2.3, "p95": 4.7, "max": 5.0})
    assert s["dy"] == pytest.approx({"mean": 1.9, "p95": 3.7, "max": 4.0})
    assert s["radial"] == pytest.approx({"mean": 3.5, "p95": 5.0, "max": 5.0})


def test_exactly_5_mm_on_one_axis_is_not_under():
    """Strictly less than, on both axes: the row at dX +5.0 does not count."""
    assert summarise(ROWS, [False] * 4)["under"] == 3
    assert summarise([[0.0, -5.0, 5.0]], [False])["under"] == 0
    assert summarise([[4.99, -4.99, 7.06]], [False])["under"] == 1


def test_nothing_matched_is_no_statistic():
    assert summarise(np.zeros((0, 3)), []) == {"n": 0, "on_target": 0}


def _entry(file, role):
    return {"file": file, "role": role, "capture_setup": "x", "window": [0, 1]}


def test_sealed_recordings_are_skipped_by_role_before_anything_is_opened(tmp_path):
    """The recordings do not exist here: choosing must not need to open them
    (ADR-0005). A Sealed one with a truth folder is skipped and named; one with
    no truth folder is not a candidate at all."""
    for name in ("camb-1", "camb-2", "cama-3"):
        (tmp_path / name).mkdir()
    entries = {"a": _entry("CamB_1.mkv", "sealed"),
               "b": _entry("CamB_2.mkv", "threshold-work"),
               "c": _entry("CamA_3.mkv", "spent"),
               "d": _entry("CamA_4.mkv", "spent"),
               "e": _entry("CamA_5.mkv", "sealed")}
    chosen, sealed = select(entries, str(tmp_path))
    assert [e["file"] for e in chosen] == ["CamA_3.mkv", "CamB_2.mkv"]
    assert sealed == ["CamB_1.mkv"]
