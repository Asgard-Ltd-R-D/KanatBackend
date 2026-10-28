"""Checks for ground-truth scoring. No model, no video, no torch."""
import argparse

import cv2
import numpy as np
import pytest

from detection import board
from detection import new_bullet_holes as nbh
from tools import manifest
from tools.evaluate import (DERIVED_NAME, DETECTOR, DISPLACEMENT, PRE_EXISTING_FIELD,
                      RAW_NAMES, SOURCE_NAME, UNKNOWN, Move, first_moved_index,
                      attribute, in_the_baseline, load_labels, match, off_canvas,
                      open_moved, parse_move, placement_note, position_errors,
                      pre_existing_labels, refuse_move, register_photograph, score,
                      score_recording)


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
    """An export was seen ended mid-number. Dropping the instance would
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


# --- Position Error --------------------------------------------------------
#
# Template px, whose y grows downward, against the printed Target's axes: X
# right, Y up, system minus truth (SOW 2.3.2, #123).


def test_a_bullet_hole_found_right_of_and_above_its_truth_errs_plus_on_both_axes():
    """10 template px right and 10 up, at 0.2 mm per template px."""
    truth = np.float32([[100, 100]])
    found = np.float32([[110, 90]])
    errors = position_errors(truth, found, score(truth, found)["pairs"], 0.2)
    np.testing.assert_allclose(errors, [[2.0, 2.0, 2.8284271]], atol=1e-6)


def test_position_error_follows_each_pair_not_the_index():
    """Found #1 is truth #2's: the error is taken across the pair, in the order
    scoring returns the pairs."""
    truth = np.float32([[0, 0], [200, 200]])
    found = np.float32([[195, 212], [3, 4], [900, 900]])
    errors = position_errors(truth, found, score(truth, found)["pairs"], 0.5)
    np.testing.assert_allclose(errors, [[-2.5, -6.0, 6.5], [1.5, -2.0, 2.5]],
                               atol=1e-6)


def test_no_pairs_is_no_position_error():
    errors = position_errors(np.float32([[0, 0]]), np.zeros((0, 2), np.float32),
                             [], 0.2)
    assert errors.shape == (0, 3)


# --- attributing false positives ------------------------------------------
#
# Positions are template px and the default tolerance is 40, so a mark is
# "displaced" out to 40 and "the detector's" past 80.


def _attribute(found, baseline, tolerance=40):
    """Attribute a run that matched no label, so every detection is a false
    positive."""
    return attribute(found, [], baseline, tolerance)


def test_a_false_positive_on_a_pre_existing_mark_is_displacement():
    """The CamB 25.60s case: a mark already on the Board, reported as new once
    registration moved it past the suppression radius."""
    got = _attribute(np.float32([[23, 0]]), np.float32([[0, 0]]))
    assert [(i, c) for i, c, _ in got] == [(0, DISPLACEMENT)]


def test_a_false_positive_far_from_every_mark_is_the_detector():
    got = _attribute(np.float32([[200, 0]]), np.float32([[0, 0]]))
    assert [(i, c) for i, c, _ in got] == [(0, DETECTOR)]


def test_unknown_is_reachable():
    """Not a rounding of the evidence. Nothing bounds how far registration can
    displace a mark — the residual that would is censored at the match radius
    on both labelled clips — so a false positive one and a half Bullet Hole
    widths from a pre-existing mark is neither cause, and is reported as
    neither."""
    got = _attribute(np.float32([[60, 0]]), np.float32([[0, 0]]))
    assert [(i, c) for i, c, _ in got] == [(0, UNKNOWN)]


def test_with_nothing_on_the_board_every_false_positive_is_the_detector():
    """No mark was there for registration to move."""
    got = _attribute(np.float32([[5, 0]]), np.zeros((0, 2), np.float32))
    assert [(i, c) for i, c, _ in got] == [(0, DETECTOR)]


def test_attribution_is_exactly_the_false_positives_and_changes_no_count():
    """One entry per false positive, none for a credited detection, and the
    headline is `score`'s regardless. A breakdown that moved the counts would
    make every earlier score incomparable."""
    truth = np.float32([[0, 0]])
    found = np.float32([[1, 0], [23, 300], [300, 300]])
    baseline = np.float32([[0, 300]])
    result = score(truth, found, tolerance=40)
    got = attribute(found, result["pairs"], baseline, tolerance=40)
    assert result["tp"] == 1 and result["fp"] == 2 and result["fn"] == 0
    assert [(i, c) for i, c, _ in got] == [(1, DISPLACEMENT), (2, DETECTOR)]
    assert len(got) == result["fp"]


def test_a_baseline_of_boxes_is_read_as_marks():
    """`process` hands over its baseline as (cx, cy, w, h). Read blindly as
    pairs, each mark reshapes into two points that are nowhere on the Board and
    every attribution is wrong."""
    boxes = np.float32([[0, 0, 9, 9], [300, 300, 9, 9]])
    assert [(i, c) for i, c, _ in _attribute(np.float32([[23, 0]]), boxes)] \
        == [(0, DISPLACEMENT)]


# --- a missed truth on a Baseline Mark (#163) -------------------------------

def test_a_missed_truth_on_a_baseline_mark_names_that_mark():
    """A Bullet Hole from an earlier Range, on the Board at `--start`: this
    Range rightly never reported it, and the score says which mark it is (P2,
    the mark's index plus one)."""
    truth = np.float32([[0, 0], [500, 500]])
    baseline = np.float32([[300, 300, 9, 9], [495, 510, 9, 9]])
    assert [(j, k) for j, k, _ in in_the_baseline(truth, [1], baseline, 40)] == [(1, 1)]


def test_a_missed_truth_beyond_tolerance_of_every_baseline_mark_is_not_named():
    truth = np.float32([[0, 0]])
    assert in_the_baseline(truth, [0], np.float32([[41, 0, 9, 9]]), 40) == []
    assert in_the_baseline(truth, [0], np.zeros((0, 4), np.float32), 40) == []


# --- moving the Board (#164) -------------------------------------------------


class _Capture:
    """A capture over `frames`, read as `Recording.open` reads a file: frame 0
    at `--start`, then each in turn, `grab` passing one undecoded."""
    def __init__(self, frames):
        self.frames, self.at = frames, 0

    def read(self):
        if self.at >= len(self.frames):
            return False, None
        self.at += 1
        return True, self.frames[self.at - 1].copy()

    def grab(self):
        return self.read()[0]

    def get(self, prop):
        return 25.0

    def set(self, prop, value):
        pass

    def release(self):
        pass


def _noise(n, size=(40, 60)):
    """`n` frames of texture with no black pixel in them."""
    rng = np.random.default_rng(164)
    return [rng.integers(1, 256, (*size, 3), dtype=np.uint8) for _ in range(n)]


def _moved(monkeypatch, frames, move, stride=1, baseline_frames=1):
    """Frame 0 and the frames handed over after it, with `frames` read from
    `--start` 10 s at 25 fps and the Board moved by `move`."""
    monkeypatch.setattr(nbh.cv2, "VideoCapture", lambda video: _Capture(frames))
    source, base = open_moved(move, "clip.mkv", 10.0)
    source.start(len(frames), stride, baseline_frames)
    return base, list(iter(source.read, None))


def test_frames_before_the_move_come_through_identical(monkeypatch):
    """Board space, the baseline and the truth placement are the unmoved run's."""
    frames = _noise(10)
    base, handed = _moved(monkeypatch, frames, Move(10.2, 3, -2))   # from frame 5
    assert np.array_equal(base, frames[0])
    assert [f.index for f in handed] == list(range(1, 10))
    assert all(np.array_equal(f.image, frames[f.index]) for f in handed if f.index < 5)
    assert not any(np.array_equal(f.image, frames[f.index]) for f in handed if f.index >= 5)


def test_from_the_move_on_an_integer_shift_is_pixel_exact_inside_the_frame(monkeypatch):
    frames = _noise(10)
    _, handed = _moved(monkeypatch, frames, Move(10.2, 3, -2))
    for f in handed[4:]:   # frames 5-9: 3 px right, 2 px up
        assert np.array_equal(f.image[:-2, 3:], frames[f.index][2:, :-3])


def test_the_vacated_border_replicates_the_edge(monkeypatch):
    """Not black: the move adds no hard edge the scene never had."""
    frames = _noise(10)
    _, handed = _moved(monkeypatch, frames, Move(10.2, 3, -2))
    moved, frame = handed[-1].image, frames[handed[-1].index]
    assert np.array_equal(moved[:-2, :3], np.repeat(frame[2:, :1], 3, axis=1))
    assert np.array_equal(moved[-2:, 3:], np.repeat(frame[-1:, :-3], 2, axis=0))


def _targets():
    """Grey, with two green Targets well off the frame's centre."""
    frame = np.full((240, 320, 3), 128, np.uint8)
    cv2.rectangle(frame, (30, 30), (110, 130), (0, 200, 0), -1)
    cv2.rectangle(frame, (150, 40), (230, 120), (0, 200, 0), -1)
    return frame


def _centroid_of_targets(frame):
    moments = [cv2.moments(c) for c in board.find_targets(frame)[0]]
    return np.mean([[m["m10"] / m["m00"], m["m01"] / m["m00"]] for m in moments], axis=0)


def test_a_rotation_keeps_the_targets_centroid_fixed(monkeypatch):
    """A rotation of the Board, not a rotation plus a hidden shift: turned
    about the frame's centre instead, this one moves it ~9 px."""
    frames = [_targets()] * 3
    _, handed = _moved(monkeypatch, frames, Move(10.04, 0, 0, 10))   # from frame 1
    turned = handed[-1].image
    assert not np.array_equal(turned, frames[0])
    assert np.linalg.norm(_centroid_of_targets(turned) - _centroid_of_targets(frames[0])) < 1


def test_under_a_stride_the_indices_handed_over_are_unchanged(monkeypatch):
    _, handed = _moved(monkeypatch, _noise(12), Move(10.2, 3, -2), stride=3, baseline_frames=2)
    assert [f.index for f in handed] == [1, 3, 6, 9]


def test_a_move_is_a_time_and_a_shift_with_an_optional_rotation():
    assert parse_move("25:80,40") == Move(25.0, 80.0, 40.0, 0.0)
    assert parse_move("29.8:-16,8,2") == Move(29.8, -16.0, 8.0, 2.0)


@pytest.mark.parametrize("text", ["25", "25:80", "25:80,40,2,1", "t:80,40",
                                  "25:80,40,nan", "25;80,40"])
def test_a_move_that_does_not_parse_is_refused(text):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_move(text)


def _refuse(at, stride=1):
    """`refuse_move` on a run from 20 s to 46 s at 25 fps, 5 baseline frames."""
    refuse_move(Move(at, 80, 40), 20, 46, 25.0, 5, stride)


def test_a_move_inside_the_baseline_window_is_refused():
    """At 25 fps the 5 baseline frames from 20 s are 20.00-20.16 s. A move
    after the last, even between two frames, first reaches 20.20 s."""
    with pytest.raises(SystemExit, match="baseline"):
        _refuse(20.16)
    _refuse(20.17)


def test_a_move_reaching_no_frame_the_run_looks_at_is_refused():
    """At or after `--end`, or past the last frame looked at: it would move
    nothing, and a case that moves nothing must not pass. At 25 fps the run's
    last frame is 45.96 s, and at stride 17 its last Look 45.84 s."""
    for at, stride in [(46, 1), (45.97, 1), (45.85, 17)]:
        with pytest.raises(SystemExit, match="--end"):
            _refuse(at, stride)
    _refuse(45.96)
    _refuse(45.84, stride=17)


@pytest.mark.parametrize("move", [Move(25, 0, 0), Move(25, 0, 0, 360), Move(25, 0, 0, -720)])
def test_a_move_that_moves_no_pixel_is_refused(move):
    """It would score the unmoved run, and a case that moves nothing must not pass."""
    with pytest.raises(SystemExit, match="no pixel"):
        refuse_move(move, 20, 46, 25.0, 5, 1)
    refuse_move(move._replace(deg=1), 20, 46, 25.0, 5, 1)


def test_a_move_starts_on_the_frame_the_log_prints_at_its_time():
    """At 30.004 fps from 20 s, frame 2 is 20.0667 s and printed 20.07 s: a move
    at 20.07 s, read off the log, starts there and not one Look late."""
    assert first_moved_index(20.07, 20, 30.004) == 2
    assert first_moved_index(20.071, 20, 30.004) == 3
    assert first_moved_index(20.2, 20, 25.0) == 5   # not frame 6 by float error
    assert first_moved_index(20.17, 20, 25.0) == 5
    assert first_moved_index(20, 20, 25.0) == 0


class _Opened(Exception):
    """Raised in place of opening the recording: everything before it ran."""


def _opened(*args, **kwargs):
    raise _Opened


class _Clip25:
    """A container that gives 25 fps, and no frame."""
    def __init__(self, path):
        pass

    def get(self, prop):
        return 25.0

    def release(self):
        pass


def test_an_unlisted_recording_runs_in_template_px_and_says_why(monkeypatch, capsys):
    """ADR-0010: no recording is refused. Unlisted, it has no Capture Setup,
    so no print scale unless --mm-per-px gives one."""
    monkeypatch.setattr(manifest, "lookup", lambda video: None)
    monkeypatch.setattr(cv2, "VideoCapture", _Clip25)
    monkeypatch.setattr(nbh, "load_model", lambda path: None)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", _opened)
    with pytest.raises(_Opened):
        score_recording("clip.mkv", 20, 46, "truth")
    assert "no Capture Setup" in capsys.readouterr().out
    with pytest.raises(_Opened):
        score_recording("clip.mkv", 20, 46, "truth", mm_per_px=0.2)
    assert "no Capture Setup" not in capsys.readouterr().out


def test_an_unlisted_recording_without_a_frame_rate_fails_before_opening(monkeypatch):
    """Its times divide by the frame rate the container gives; 0 must not reach them."""
    monkeypatch.setattr(manifest, "lookup", lambda video: None)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", _opened)
    with pytest.raises(SystemExit, match="frame rate"):
        score_recording("no-such-clip.mkv", 20, 46, "truth", mm_per_px=0.2)


def test_a_listed_capture_setup_without_a_print_scale_is_still_refused(monkeypatch):
    """Listed, the recording's millimetres are its Capture Setup's, never guessed."""
    monkeypatch.setattr(board, "print_scales", lambda: {})
    monkeypatch.setattr(manifest, "lookup",
                        lambda video: {"capture_setup": "setup", "fps": 25.0})
    monkeypatch.setattr(nbh, "load_model", lambda path: None)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", _opened)
    with pytest.raises(SystemExit, match="no print scale"):
        score_recording("clip.mkv", 20, 46, "truth")
    with pytest.raises(_Opened):
        score_recording("clip.mkv", 20, 46, "truth", mm_per_px=0.2)


# --- placing photograph truth through the baseline frame -------------------

def _scene():
    """A textured Board with a small green disk for artwork.

    A disk's outline says nothing about rotation, so a registration fitted to
    the artwork alone is free to turn about it and lands everything away from
    the disk in the wrong place — the extrapolation #40 is about, in miniature.
    """
    rng = np.random.default_rng(0)
    noise = cv2.GaussianBlur(rng.random((700, 1200)).astype(np.float32), (0, 0), 12)
    grey = cv2.normalize(noise, None, 90, 230, cv2.NORM_MINMAX).astype(np.uint8)
    image = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
    cv2.circle(image, (250, 350), 90, (60, 160, 30), -1)
    return image


def test_a_photograph_registers_to_the_frame_far_from_the_artwork():
    """Fitted to the artwork alone this scene misses by 18.6 px at correlation
    0.9999. The bound is the blur's price in precision, ~3 px here."""
    photo = _scene()
    true = np.float32([[0.97, -0.06, 60], [0.05, 0.98, 30], [2e-5, 1e-5, 1]])
    frame = cv2.warpPerspective(photo, true, (1300, 800))
    far = np.float32([[1100, 80], [1100, 620], [700, 350]])

    def miss(H):
        return np.abs(board.apply(H, far) - board.apply(true, far)).max()

    photo_targets, photo_mask = board.find_targets(photo)
    frame_targets, frame_mask = board.find_targets(frame)
    artwork_only, _ = board.register(photo_mask, frame_mask, frame_targets[0])
    assert miss(artwork_only) > 10
    assert miss(register_photograph(photo, frame)[0]) < 5


def test_registration_survives_the_largest_target_changing():
    """Two Targets, and a viewpoint that makes the photograph's smaller one the
    frame's largest. Seeded largest-to-largest this lands ~1400 px out."""
    photo = _scene()
    cv2.circle(photo, (850, 350), 86, (60, 160, 30), -1)
    true = np.float32([[1.0, 0, 40], [0, 1.0, 20], [-2e-4, 0, 1]])
    frame = cv2.warpPerspective(photo, true, (1600, 900))
    far = np.float32([[1100, 80], [1100, 620], [700, 350], [100, 100]])
    H, _ = register_photograph(photo, frame)
    assert np.abs(board.apply(H, far) - board.apply(true, far)).max() < 5


def test_registration_survives_the_largest_target_being_cropped_out():
    """The photograph's largest Target is outside the frame. Seeded from it,
    whichever frame Target it is paired with, this lands ~480 px out."""
    photo = _scene()
    cv2.circle(photo, (850, 350), 86, (60, 160, 30), -1)
    true = np.float32([[1.0, 0.03, -480], [-0.02, 1.0, 20], [1e-5, 0, 1]])
    frame = cv2.warpPerspective(photo, true, (720, 700))
    far = np.float32([[1100, 80], [1100, 620], [700, 350], [600, 600]])
    H, _ = register_photograph(photo, frame)
    assert np.abs(board.apply(H, far) - board.apply(true, far)).max() < 5


def test_a_label_off_the_rectified_board_is_named():
    view = board.BoardView(H=np.eye(3, dtype=np.float32),
                           tpl_to_board=board._as_matrix(0.5, (10, 10)),
                           canvas_size=(500, 400), targets=[])
    truth = np.float32([[100, 100], [-40, 100], [100, 790], [100, 770]])
    assert off_canvas(truth, view) == [1, 2]


def test_derived_truth_names_its_pre_existing_marks(tmp_path):
    """The after export's lines the derivation recorded as pre-existing — not
    the export minus the derived file. Here the new label was corrected, so
    it no longer equals its export line, and the subtraction would count it
    as pre-existing too."""
    (tmp_path / RAW_NAMES["after"]).write_text(
        "0 0.1 0.1 0.01 0.01\n0 0.5 0.5 0.01 0.01\n0 0.9 0.2 0.01 0.01\n")
    (tmp_path / DERIVED_NAME).write_text("0 0.52 0.5 0.01 0.01\n")
    (tmp_path / SOURCE_NAME).write_text(f"{PRE_EXISTING_FIELD}: 1,3\n")
    got = pre_existing_labels(str(tmp_path / DERIVED_NAME))
    np.testing.assert_allclose(got, [[0.1, 0.1], [0.9, 0.2]], atol=1e-6)


def test_a_derivation_without_the_record_names_no_pre_existing_marks(tmp_path):
    (tmp_path / RAW_NAMES["after"]).write_text("0 0.1 0.1 0.01 0.01\n")
    (tmp_path / DERIVED_NAME).write_text("")
    (tmp_path / SOURCE_NAME).write_text("pre-existing: 1\n")
    assert pre_existing_labels(str(tmp_path / DERIVED_NAME)) is None


def test_truth_not_derived_has_no_pre_existing_marks(tmp_path):
    labels = tmp_path / "board.txt"
    labels.write_text("0 0.5 0.5 0.01 0.01\n")
    assert pre_existing_labels(str(labels)) is None


def test_off_canvas_pre_existing_marks_stay_a_placement_doubt():
    """_103223: two pre-existing marks below the canvas no baseline can hold.
    A wrong placement could have thrown them there, so the on-canvas match
    alone is not a clean placement (#41)."""
    note = placement_note(np.float32([[0, 0]]), np.float32([[3, 4]]),
                          40.0, 0.2, off_canvas_count=2)
    assert "1 of 1" in note
    assert "[WARN] 2 more pre-existing mark(s) land off the canvas" in note


def test_placement_is_unverified_when_every_pre_existing_mark_is_off_canvas():
    """Nothing left to check against is not "0 of 0 land within" — say so."""
    note = placement_note(np.zeros((0, 2), np.float32), np.float32([[3, 4]]),
                          40.0, 0.2, off_canvas_count=2)
    assert "placement unverified" in note
    assert "2 pre-existing mark(s)" in note


def test_the_placement_range_is_stated_in_mm_too():
    """The placement's own error sits inside every Position Error measured
    against this truth, so it is read in the same unit (#124)."""
    note = placement_note(np.float32([[0, 0], [100, 0]]),
                          np.float32([[3, 4], [100, 10]]), 40.0, 0.2)
    assert "5-10 px (1.0-2.0 mm)" in note
    note = placement_note(np.float32([[0, 0], [100, 0]]),
                          np.float32([[3, 4], [100, 10]]), 40.0, None)
    assert "5-10 px: that is" in note   # no print scale, no mm
