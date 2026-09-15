"""Checks for ground-truth scoring. No model, no video, no torch."""
import numpy as np
import pytest

from evaluate import load_labels, match, score


def test_greedy_matching_is_one_to_one():
    """Without this, a cluster of false positives all credit the same label and
    precision reads far better than it is."""
    truth = np.float32([[0, 0]])
    found = np.float32([[1, 0], [2, 0], [3, 0]])
    result = score(truth, found, tolerance=10)
    assert result["tp"] == 1
    assert result["fp"] == 2


def test_nearest_detection_wins_the_label():
    truth = np.float32([[0, 0]])
    found = np.float32([[9, 0], [1, 0]])
    pairs, _ = match(truth, found, tolerance=10)
    assert pairs == [(1, 0, pytest.approx(1.0))]


def test_detection_beyond_tolerance_is_a_false_positive():
    result = score(np.float32([[0, 0]]), np.float32([[100, 0]]), tolerance=40)
    assert result["tp"] == 0 and result["fp"] == 1 and result["fn"] == 1


def test_perfect_run_scores_one():
    pts = np.float32([[0, 0], [100, 100]])
    result = score(pts, pts.copy(), tolerance=10)
    assert result["f1"] == 1.0
    assert result["precision"] == 1.0 and result["recall"] == 1.0


def test_finding_nothing_is_not_a_pass():
    result = score(np.float32([[0, 0]]), np.zeros((0, 2), np.float32), tolerance=10)
    assert result["f1"] == 0.0 and result["fn"] == 1


def test_box_format_is_read_as_centres(tmp_path):
    """class cx cy w h — five fields on every line means a detection export."""
    f = tmp_path / "labels.txt"
    f.write_text("0 0.25 0.75 0.02 0.03\n0 0.5 0.5 0.02 0.02")
    centres, damaged = load_labels(str(f))
    assert damaged == 0
    assert centres[0] == pytest.approx([0.25, 0.75])
    assert centres[1] == pytest.approx([0.5, 0.5])


def test_five_fields_among_polygons_is_damaged_not_a_box(tmp_path):
    """The same line shape means different things in different files."""
    f = tmp_path / "labels.txt"
    f.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n0 0.5 0.5 0.6 0.5")
    centres, damaged = load_labels(str(f))
    assert len(centres) == 1 and damaged == 1


def test_truncated_label_is_kept_not_dropped(tmp_path):
    """The KanatV6 export ended mid-number. Dropping the instance would
    understate ground truth, which flatters recall."""
    f = tmp_path / "labels.txt"
    f.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n"
                 "0 0.5 0.5 0.6 0.5 0.6 0.6 0.04")
    centroids, damaged = load_labels(str(f))
    assert len(centroids) == 2
    assert damaged == 1


def test_label_too_short_to_be_a_polygon_is_counted_as_damaged(tmp_path):
    f = tmp_path / "labels.txt"
    f.write_text("0 0.1 0.1 0.2")
    centroids, damaged = load_labels(str(f))
    assert len(centroids) == 0 and damaged == 1
