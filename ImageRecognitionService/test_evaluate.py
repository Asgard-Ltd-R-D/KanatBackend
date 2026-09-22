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
    """class cx cy w h — four values after the class is a box."""
    f = tmp_path / "labels.txt"
    f.write_text("0 0.25 0.75 0.02 0.03\n0 0.5 0.5 0.02 0.02")
    centres, damaged = load_labels(str(f))
    assert damaged == 0
    assert centres[0] == pytest.approx([0.25, 0.75])
    assert centres[1] == pytest.approx([0.5, 0.5])


def test_a_box_among_polygons_is_read_as_a_box(tmp_path):
    """Roboflow exports an annotation drawn as a box this way, and five of six
    files in one delivery arrived so. The rule is per line: four values is a
    box wherever it sits. Dropping it, as the old per-file rule did, takes a
    mark out of ground truth and flatters recall."""
    f = tmp_path / "labels.txt"
    f.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n0 0.5 0.5 0.02 0.03")
    centres, damaged = load_labels(str(f))
    assert len(centres) == 2 and damaged == 0
    assert centres[1] == pytest.approx([0.5, 0.5])


def test_a_truncated_line_is_still_damaged(tmp_path):
    """An odd number of values is a coordinate cut short, not a box."""
    f = tmp_path / "labels.txt"
    f.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n0 0.5 0.5 0.6 0.5 0.6")
    _, damaged = load_labels(str(f))
    assert damaged == 1


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


def test_a_crossed_pair_costs_nothing():
    """Nearest-first alone manufactures a false positive and a false negative.

    Labels at 0 and 10, detections at 4 and -5, tolerance 7. The detection at 4
    is nearest to label 0 and takes it, leaving -5 with nothing in reach — one
    true positive. Pairing -5 with 0 and 4 with 10 credits both, and both are
    within tolerance. Thresholds get set from these counts.
    """
    truth = np.float32([[0, 0], [10, 0]])
    found = np.float32([[4, 0], [-5, 0]])
    result = score(truth, found, tolerance=7)
    assert result["tp"] == 2
    assert result["fp"] == 0 and result["fn"] == 0


def test_re_routing_never_costs_a_pair():
    """A detection that can only reach one label keeps it.

    The chain has to stop somewhere: detection 0 reaches both labels, detection
    1 reaches only label 0. Handing label 0 to detection 1 is what lets both
    score, but only because detection 0 has somewhere else to go.
    """
    truth = np.float32([[0, 0], [10, 0]])
    found = np.float32([[5, 0], [0, 0]])
    pairs, missed = match(truth, found, tolerance=6)
    assert sorted(j for _, j, _ in pairs) == [0, 1]
    assert missed == []


def test_a_detection_out_of_reach_of_everything_is_still_a_false_positive():
    """Maximum cardinality must not mean reaching past the tolerance."""
    result = score(np.float32([[0, 0]]), np.float32([[1, 0], [500, 0]]), tolerance=10)
    assert result["tp"] == 1 and result["fp"] == 1


def test_the_nearer_pairing_wins_when_both_score_the_same():
    """Which mark is left over is the answer, not a tie-break.

    Before-marks at 0 and 6, after-marks at 0, 1 and 4: pairing {0-0, 6-4}
    and pairing {0-1, 6-0} both score two, and they disagree about which
    after-mark is new. `derive_new_holes` writes that leftover into the ground
    truth, so the nearer pairing has to win.
    """
    truth = np.float32([[0, 0], [0, 6]])
    found = np.float32([[0, 0], [0, 1], [0, 4]])
    pairs, missed = match(truth, found, tolerance=6)
    assert [(i, j) for i, j, _ in pairs] == [(0, 0), (2, 1)]
    assert missed == []
