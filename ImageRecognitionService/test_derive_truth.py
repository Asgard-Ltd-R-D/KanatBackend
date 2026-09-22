"""Checks for photograph-derived ground truth, the derivation in evaluate.py.

No model, no video, no torch.

The CamB case at the end does read two real files and registers a photograph,
which costs about a second — it is the case that was got wrong by hand, so it
is pinned against the files rather than against a fixture.
"""
import os

import numpy as np
import pytest

import evaluate

TOL = 40.0
TRUTH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "truth")


def _truth(*parts):
    return os.path.join(TRUTH_DIR, *parts)


def _pts(*xy):
    return np.array(xy, np.float32).reshape(-1, 2)


# --- the set difference ----------------------------------------------------

def test_a_mark_in_both_photographs_is_not_new():
    assert evaluate.new_label_indices(_pts((100, 100)), _pts((100, 100)), TOL) == []


def test_a_mark_only_in_the_after_photograph_is_new():
    assert evaluate.new_label_indices(
        _pts((100, 100)), _pts((100, 100), (500, 500)), TOL) == [1]


def test_a_mark_only_in_the_before_photograph_subtracts_nothing():
    """A mark that was chipped out, or a label the annotator drew and the
    after pass missed. It must not crash, and it must not consume a new mark."""
    assert evaluate.new_label_indices(
        _pts((100, 100), (900, 900)), _pts((500, 500)), TOL) == [0]


def test_nothing_labelled_before_makes_every_mark_new():
    """The Board was clean. Empty is a legitimate before-export, not a failure."""
    after = _pts((100, 100), (500, 500))
    assert evaluate.new_label_indices(
        np.zeros((0, 2), np.float32), after, TOL) == [0, 1]


def test_a_mark_that_shifted_between_photographs_is_still_one_mark():
    """The two photographs are taken from different positions and registered
    separately, so the same mark lands a few px apart. Inside the tolerance
    that is one mark, not one pre-existing plus one new."""
    assert evaluate.new_label_indices(_pts((100, 100)), _pts((130, 100)), TOL) == []


def test_two_distinct_marks_near_one_pre_existing_are_not_folded_together():
    """A Bullet Hole landing next to a pre-existing mark is the case this set
    difference exists to get right: one-to-one matching means the pre-existing
    label is spent once, and the second mark stays new."""
    assert evaluate.new_label_indices(
        _pts((100, 100)), _pts((100, 100), (135, 100)), TOL) == [1]


def test_a_mark_beyond_the_tolerance_is_a_different_mark():
    assert evaluate.new_label_indices(_pts((100, 100)), _pts((100, 200)), TOL) == [0]


# --- reading the export ----------------------------------------------------

def test_a_box_export_is_read_line_for_line(tmp_path):
    f = tmp_path / "labels.txt"
    f.write_text("0 0.25 0.75 0.02 0.03\n0 0.5 0.5 0.02 0.02\n")
    lines, centres = evaluate.read_export(str(f))
    assert len(lines) == 2 and len(centres) == 2
    assert centres[0] == pytest.approx([0.25, 0.75])


def test_a_polygon_export_is_read_line_for_line(tmp_path):
    f = tmp_path / "labels.txt"
    f.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n"
                 "0 0.5 0.5 0.6 0.5 0.6 0.6 0.5 0.6\n")
    lines, centres = evaluate.read_export(str(f))
    assert len(lines) == 2 and len(centres) == 2


def test_a_box_among_polygons_is_read_and_reported(tmp_path):
    """Roboflow exports one annotation drawn as a box this way, and most files
    in both deliveries arrived so. Refusing the file, or reading it one label
    short, both cost a mark: the first stops the derivation, the second lets a
    pre-existing mark through as new. So it is read, and the mix is reported."""
    f = tmp_path / "labels.txt"
    f.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n"
                 "0 0.42 0.43 0.006 0.009\n")
    lines, centres = evaluate.read_export(str(f))
    assert len(lines) == 2 and len(centres) == 2
    assert evaluate.box_lines(lines) == [2]
    assert centres[1] == pytest.approx([0.42, 0.43])


def test_a_truncated_polygon_is_refused(tmp_path):
    """One export was seen cut off mid-number. That is a wrong position, not
    a differently drawn one, so the derivation refuses it."""
    f = tmp_path / "labels.txt"
    f.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n"
                 "0 0.5 0.5 0.6 0.5 0.6 0.6 0.04\n")
    with pytest.raises(SystemExit) as refused:
        evaluate.read_export(str(f))
    assert "line 2" in str(refused.value)


def test_an_empty_export_reads_as_no_marks(tmp_path):
    f = tmp_path / "labels.txt"
    f.write_text("\n")
    lines, centres = evaluate.read_export(str(f))
    assert lines == [] and len(centres) == 0


# --- the tolerance, carried into the photograph's frame --------------------

def test_the_tolerance_is_the_same_physical_slack_in_photograph_px():
    """40 template px is one Bullet Hole's width. The Target in these customer
    photographs spans about a sixth of the template, so the same slack is about
    six photo px — matching at 40 photo px there would fold distinct marks
    together."""
    assert evaluate.photo_tolerance(40.0, target_span_px=160.0,
                                    template_span_px=1049.0) == pytest.approx(6.1,
                                                                              abs=0.1)


def test_a_photograph_at_template_scale_keeps_the_template_tolerance():
    assert evaluate.photo_tolerance(40.0, 1049.0, 1049.0) == 40.0


# --- the CamB case, pinned by name ----------------------------------------

def test_camb_derivation_reproduces_the_three_hand_worked_labels(tmp_path):
    """`truth/camb-25-36` is the case that was scored wrong.

    Four labels were drawn on the after photograph; one of them sits on a mark
    already on the Board at the 25s baseline frame, and scoring against all
    four reported F1 1.00 in an earlier HANDOVER revision. The three were then
    worked out by hand into `board.new-since-25s.txt`. This derives them
    instead, from the operator's before-labels, and the two files must agree.
    """
    result = evaluate.derive_new_holes(
        before_image=_truth("camb-25-36", "board.jpeg"),
        before_labels=_truth("camb-25-36", "board.before.txt"),
        after_image=_truth("camb-25-36", "board.jpeg"),
        after_labels=_truth("camb-25-36", "board.txt"))

    assert len(result["new"]) == 3
    assert len(result["pre_existing"]) == 1
    hand_worked = open(
        _truth("camb-25-36", "board.new-since-25s.txt")).read().splitlines()
    derived = [result["lines"][i] for i in result["new"]]
    assert derived == [l for l in hand_worked if l.strip()]


def test_writing_keeps_the_raw_export_byte_for_byte(tmp_path):
    """The derived file is a correction; the export it came from is evidence."""
    raw = ("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n"
           "0 0.5 0.5 0.6 0.5 0.6 0.6 0.5 0.6")   # no trailing newline
    after = tmp_path / "after.txt"
    after.write_text(raw)
    before = tmp_path / "before.txt"
    before.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n")
    result = {"lines": raw.splitlines(), "new": [1], "pre_existing": [0],
              "only_before": [], "correlation": 0.99, "tolerance_px": 6.1}

    written = evaluate.write_derived(str(tmp_path / "out"), result,
                                     "before.jpeg", str(before),
                                     "after.jpeg", str(after))

    assert open(written["derived"]).read().splitlines() == [
        "0 0.5 0.5 0.6 0.5 0.6 0.6 0.5 0.6"]
    assert open(written["after_raw"]).read() == raw
    assert open(written["before_raw"]).read() == before.read_text()


def test_the_derived_file_records_which_photograph_it_belongs_to(tmp_path):
    """Normalised coordinates mean nothing without the image they are
    normalised against, and the photographs are too large to keep in the repo."""
    after = tmp_path / "after.txt"
    after.write_text("0 0.5 0.5 0.02 0.02\n")
    before = tmp_path / "before.txt"
    before.write_text("")
    result = {"lines": ["0 0.5 0.5 0.02 0.02"], "new": [0], "pre_existing": [],
              "only_before": [], "correlation": 0.99, "tolerance_px": 6.1}

    written = evaluate.write_derived(str(tmp_path / "out"), result,
                                     "/photos/CamB.before.jpeg", str(before),
                                     "/photos/CamB.after.jpeg", str(after))

    source = open(written["source"]).read()
    assert "after-image: /photos/CamB.after.jpeg" in source
    assert "new-bullet-holes: 1" in source


# --- reading the derived truth back ----------------------------------------

def test_a_derived_truth_directory_reads_the_derived_file_not_the_export(tmp_path):
    """Both files sit in the directory and the export sorts first.

    Pointing `--truth-labels` at the directory and getting
    `board.after.export.txt` scores the run against every mark on the Board,
    pre-existing ones included — the error this whole derivation exists to
    prevent, arrived at by an alphabetical accident.
    """
    (tmp_path / evaluate.RAW_NAMES["after"]).write_text("0 0.1 0.1 0.02 0.02\n"
                                                        "0 0.5 0.5 0.02 0.02\n")
    (tmp_path / evaluate.DERIVED_NAME).write_text("0 0.5 0.5 0.02 0.02\n")
    assert evaluate.truth_labels(str(tmp_path)) == str(
        tmp_path / evaluate.DERIVED_NAME)


def test_a_directory_with_one_label_file_takes_it(tmp_path):
    (tmp_path / "board.txt").write_text("0 0.5 0.5 0.02 0.02\n")
    assert evaluate.truth_labels(str(tmp_path)) == str(tmp_path / "board.txt")


def test_a_directory_of_several_label_files_is_refused(tmp_path):
    """`truth/camb-25-36` holds four. Without the derived file to prefer there
    is no right answer to guess, and the first one alphabetically is
    `board.before.txt` — the marks that were already on the Board."""
    for name in ("board.before.txt", "board.txt"):
        (tmp_path / name).write_text("0 0.5 0.5 0.02 0.02\n")
    with pytest.raises(SystemExit) as refused:
        evaluate.truth_labels(str(tmp_path))
    assert "board.before.txt" in str(refused.value)


def test_an_unpaired_before_mark_travels_with_the_derived_file(tmp_path):
    """`board.source.txt` records it, and the scoring run is the place it
    matters: an unpaired before-mark means one of these labels was probably
    already on the Board, so the run is charged a miss it could not have made.
    A flag only the derivation prints is a flag nobody sees again."""
    labels = tmp_path / evaluate.DERIVED_NAME
    labels.write_text("0 0.5 0.5 0.02 0.02\n")
    (tmp_path / evaluate.SOURCE_NAME).write_text(
        "labelled-after: 12\nbefore-marks-without-a-counterpart: 2\n")
    assert evaluate.unpaired_before_marks(str(labels)) == 2


def test_truth_that_was_never_derived_has_nothing_to_flag(tmp_path):
    labels = tmp_path / "board.txt"
    labels.write_text("0 0.5 0.5 0.02 0.02\n")
    assert evaluate.unpaired_before_marks(str(labels)) == 0


# --- the second registration, fitted to the marks themselves ---------------

def test_a_refit_pulls_in_marks_the_artwork_registration_left_out():
    """The artwork covers a sixth of the photograph, so the homography is
    extrapolating away from it and the residual grows with distance. The marks
    it did agree on are correspondences spread over the whole Board, and a
    similarity fitted to them puts the stragglers back on their counterparts —
    at the same tolerance, so nothing new can fold together."""
    after = _pts((100, 100), (200, 100), (300, 100), (400, 100), (900, 900))
    # Every mark is displaced by a uniform 5 px, which is inside the tolerance
    # for none of them at 4, and the fit recovers it exactly.
    before = after[:4] + [5, 5]
    pairs, _ = evaluate.match(before, after, 4.0)
    assert len(pairs) == 0

    moved = evaluate.refit_on_matched_marks(
        before, after, [(i, i, 0.0) for i in range(4)])
    pairs, unmatched = evaluate.match(moved, after, 4.0)
    assert len(pairs) == 4 and unmatched == []


def test_a_refit_needs_enough_pairs_to_carry_evidence():
    """Two correspondences determine a similarity exactly, so it fits them
    perfectly and says nothing. A fit that cannot be wrong is not evidence."""
    before, after = _pts((0, 0), (10, 10)), _pts((1, 1), (11, 11))
    assert evaluate.refit_on_matched_marks(before, after,
                                           [(0, 0, 1.4), (1, 1, 1.4)]) is None



def test_a_refit_supported_by_only_two_of_its_seeds_is_refused():
    """RANSAC reaches the two-point fit the long way round.

    Four correspondences, two of which disagree with the other two: the
    similarity that fits either pair perfectly is free to call the other pair
    outliers. Counting the seeds says four, counting the inliers says two, and
    two correspondences determine a similarity exactly — the fit reproduces
    its own input and is not evidence of anything.
    """
    before = _pts((0, 0), (100, 0), (0, 100), (100, 100))
    after = _pts((0, 0), (100, 0), (900, 700), (150, 480))
    assert evaluate.refit_on_matched_marks(
        before, after, [(i, i, 0.0) for i in range(4)]) is None


def test_a_refit_that_only_re_deals_the_same_pairs_is_not_adopted():
    """A tie is not an improvement: same number of pairs, different marks,
    so a different after-label is written down as a new Bullet Hole with
    nothing gained to justify it."""
    pairs = [(0, 0, 1.0), (1, 1, 1.0)]
    assert evaluate.keep_refit(pairs, [(0, 1, 0.5), (2, 0, 0.5)]) is False
    assert evaluate.keep_refit(pairs, [(0, 0, 0.1), (1, 1, 0.1)]) is True
    assert evaluate.keep_refit(pairs, [(0, 0, 3.0)]) is False
    assert evaluate.keep_refit(pairs, [(0, 1, 1.0), (1, 0, 1.0), (2, 2, 1.0)]) is True
