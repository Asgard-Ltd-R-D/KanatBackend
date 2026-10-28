"""Checks for the Board-move measurement's verdicts (#165). No model, no video."""
import math

import pytest

from tools.board_move import compare, two_ranges
from tools.evaluate import DETECTOR, DISPLACEMENT, UNKNOWN


def _score(rows=(), times=(), false_positives=(), in_baseline=(), lost=0, reanchors=0):
    """A score result as `evaluate.score_recording` returns it, four truths;
    `rows` as `(found #, truth #, dX, dY)` mm."""
    return {"rows": [(i, j, "Target 1", dx, dy, math.hypot(dx, dy)) for i, j, dx, dy in rows],
            "times": list(times), "false_positives": list(false_positives),
            "in_baseline": list(in_baseline), "lost": lost, "reanchors": reanchors,
            "truths": 4}


# Found #1 is truth #2 at 27 s, #2 a false positive on a Baseline Mark, #3
# truth #4 at 33 s. Truths #1 and #3 are missed.
CONTROL = _score(rows=[(1, 2, 0.5, -0.5), (3, 4, 1.0, 1.0)], times=[27.0, 30.0, 33.0],
                 false_positives=[(2, (100.0, 200.0), DISPLACEMENT, 12.0)])


def test_a_case_with_its_controls_true_and_false_positives_passes():
    """The control's false positive 11 template px away is the same one, and a
    truth only the case found is reported, not judged."""
    case = _score(rows=[(1, 2, 0.8, -0.1), (2, 1, 0.0, 0.0), (4, 4, 1.0, 1.0)],
                  times=[27.68, 29.0, 31.0, 34.36],
                  false_positives=[(3, (110.0, 205.0), UNKNOWN, 50.0)], lost=6, reanchors=1)
    c = compare(CONTROL, case)
    assert c["passed"] and c["dropped"] == [] and c["extra"] == []
    by_truth = {t["truth"]: t for t in c["truths"]}
    assert by_truth[1]["control"] is None and by_truth[1]["case"] == (2, 29.0)
    assert by_truth[3]["control"] is None and by_truth[3]["case"] is None
    assert by_truth[2]["moved"] == pytest.approx((0.3, 0.4))
    assert by_truth[2]["delay"] == pytest.approx(0.68)
    assert by_truth[4]["moved"] == pytest.approx((0.0, 0.0))
    assert by_truth[4]["delay"] == pytest.approx(1.36)


def test_a_true_positive_the_control_found_and_the_case_dropped_fails():
    case = _score(rows=[(1, 2, 0.5, -0.5)], times=[27.0, 30.0],
                  false_positives=[(2, (100.0, 200.0), DISPLACEMENT, 12.0)])
    c = compare(CONTROL, case)
    assert not c["passed"] and c["dropped"] == [4] and c["extra"] == []
    assert next(t for t in c["truths"] if t["truth"] == 4)["case"] is None


@pytest.mark.parametrize("cause", [DETECTOR, UNKNOWN, DISPLACEMENT])
def test_a_false_positive_the_control_lacks_fails_whatever_attribution_calls_it(cause):
    """A Baseline Mark displaced as far as #92's case reads as the detector:
    the cause is reported, never a reason to pass."""
    extra = (3, (300.0, 200.0), cause, 200.0)
    case = _score(rows=[(1, 2, 0.5, -0.5), (4, 4, 1.0, 1.0)], times=[27.0, 30.0, 31.0, 33.0],
                  false_positives=[(2, (100.0, 200.0), DISPLACEMENT, 12.0), extra])
    c = compare(CONTROL, case)
    assert not c["passed"] and c["dropped"] == [] and c["extra"] == [extra]


RANGE_1 = _score(rows=[(1, 3, 0.2, 0.1)], times=[12.0])
RANGE_2 = _score(rows=[(1, 2, 0.5, -0.5), (3, 4, 1.0, 1.0), (4, 1, 0.0, 0.3)],
                 times=[27.0, 30.0, 33.0, 40.0], in_baseline=[(3, 3)],
                 false_positives=[(2, (100.0, 200.0), DISPLACEMENT, 12.0)])


def test_two_ranges_that_each_report_their_own_bullet_holes_pass():
    assert all(passed for _, passed in two_ranges(RANGE_1, RANGE_2))


def test_an_earlier_ranges_bullet_hole_reported_as_new_fails():
    """Truth #3 back among Range 2's new Bullet Holes, not on a P entry."""
    range_2 = dict(RANGE_2, rows=RANGE_2["rows"] + [(5, 3, 0.2, 0.1)],
                   times=RANGE_2["times"] + [45.0], in_baseline=[])
    failed = [what for what, passed in two_ranges(RANGE_1, range_2) if not passed]
    assert failed == ["Range 2 reports truth #2, #4 and #1, and no other",
                      "Range 2 names truth #3 in the baseline at --start, on a P entry"]


def test_a_bullet_hole_reported_before_it_was_fired_fails():
    """The truth is the final Board's, so a detection in Range 1 where truth #2
    will be scores as a true positive: it is one only once #2 is fired."""
    range_1 = dict(RANGE_1, rows=RANGE_1["rows"] + [(2, 2, 0.1, 0.1)],
                   times=RANGE_1["times"] + [15.0])
    failed = [what for what, passed in two_ranges(range_1, RANGE_2) if not passed]
    assert failed == ["Range 1 reports truth #3, and no other"]


