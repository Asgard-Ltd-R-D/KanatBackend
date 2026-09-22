"""Checks for baseline construction. No model, no video, no torch.

The baseline answers one question — "was this mark already on the Board?" — and
whatever it fails to see is reported as a new Bullet Hole. Measured on
`CamB_20260915_102250.mkv`: a mark 127 Board px from anything in the single
baseline frame at t=0 was missed there, detected at 0.40 from t=0.04s onward,
and reported as a new Bullet Hole 40 ms after the baseline. No bullet arrives in
one frame.
"""
import numpy as np
import pytest
from new_bullet_holes import baseline_marks, strip_pre_existing

MATCH = 2.96  # CamB's BoardView.match_radius, Board-space px


def _marks(*xy):
    """Detections as (cx, cy, w, h), boxes about one Bullet Hole wide."""
    return np.array([[x, y, 10.0, 10.0] for x, y in xy], np.float32)


def test_a_mark_the_first_frame_missed_is_still_pre_existing():
    """The CamB 0.04s defect, in miniature.

    Absent from frame 0, present in the four that follow. A single-frame
    baseline calls it new; the union does not.
    """
    frames = [_marks((207.0, 166.1))] + [
        _marks((207.0, 166.1), (169.0, 286.0)) for _ in range(4)]
    baseline = baseline_marks(frames, MATCH)

    later = _marks((207.2, 166.3), (169.4, 286.2))
    survivors, residuals = strip_pre_existing(later, baseline, MATCH)
    assert len(survivors) == 0
    assert len(residuals) == 2  # both matched, and both distances are registration error


def test_one_mark_seen_in_every_frame_is_counted_once():
    """The count printed to the operator must not multiply by frames looked at."""
    jitter = [_marks((100.0 + i * 0.3, 100.0 - i * 0.2)) for i in range(5)]
    assert len(baseline_marks(jitter, MATCH)) == 1


def test_distinct_marks_are_kept_apart():
    both = _marks((100.0, 100.0), (140.0, 100.0))
    assert len(baseline_marks([both, both], MATCH)) == 2


def test_a_genuinely_new_mark_still_survives_the_baseline():
    """The union must not swallow what arrives after it.

    The bound the other way: widening what counts as pre-existing costs recall
    directly, which is the trap ADR-0003 records for the 40 template-px radius.
    """
    frames = [_marks((100.0, 100.0)) for _ in range(5)]
    baseline = baseline_marks(frames, MATCH)

    later = _marks((100.1, 100.2), (140.0, 100.0))
    survivors, residuals = strip_pre_existing(later, baseline, MATCH)
    assert len(survivors) == 1
    assert survivors[0][0] == 140.0
    assert residuals == pytest.approx([0.2236], abs=1e-3)  # the suppressed one


def test_an_empty_baseline_strips_nothing():
    later = _marks((100.0, 100.0))
    survivors, residuals = strip_pre_existing(later, baseline_marks([], MATCH), MATCH)
    assert len(survivors) == 1
    assert len(residuals) == 0


def test_a_baseline_frame_with_no_detections_is_harmless():
    """A clean Board, or a frame the model found nothing in, is ordinary.

    It contributes nothing and must not break the union — the first baseline
    frame of a fresh Board has exactly this shape.
    """
    empty = np.zeros((0, 4), np.float32)
    assert len(baseline_marks([empty, empty], MATCH)) == 0
    assert len(baseline_marks([empty, _marks((100.0, 100.0)), empty], MATCH)) == 1


def test_no_detections_in_a_later_frame_strips_to_nothing():
    baseline = baseline_marks([_marks((100.0, 100.0))], MATCH)
    survivors, residuals = strip_pre_existing(np.zeros((0, 4), np.float32), baseline, MATCH)
    assert len(survivors) == 0 and len(residuals) == 0
