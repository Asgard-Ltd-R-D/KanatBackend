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


def test_a_box_among_polygons_is_refused_by_line_number(tmp_path):
    """Roboflow exports one annotation drawn as a box this way, and the CamB
    export arrived so. Reading it as a polygon drops the label, and a dropped
    label flatters recall — so the file is reported, not quietly reduced."""
    f = tmp_path / "labels.txt"
    f.write_text("0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n"
                 "0 0.42 0.43 0.006 0.009\n")
    with pytest.raises(SystemExit) as refused:
        evaluate.read_export(str(f))
    assert "line 2" in str(refused.value)


def test_a_truncated_polygon_is_refused(tmp_path):
    """One export was seen cut off mid-number."""
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

    out = tmp_path / "out"
    written = evaluate.write_derived(str(out), lines=raw.splitlines(), new=[1],
                                     before_labels=str(before),
                                     after_labels=str(after))

    assert open(written["derived"]).read().splitlines() == [
        "0 0.5 0.5 0.6 0.5 0.6 0.6 0.5 0.6"]
    assert open(written["after_raw"]).read() == raw
    assert open(written["before_raw"]).read() == before.read_text()
