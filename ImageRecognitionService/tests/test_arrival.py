"""Checks for #273's arrival proposal. No model, no video."""
import numpy as np

from tools import arrival


def _series(n=200, at=120, before=1.0, after=9.0, noise=0.3, seed=0):
    d = np.full(n, before) + np.random.default_rng(seed).normal(0, noise, n)
    d[at:] += after - before
    return d


def test_a_clean_step_is_proposed_at_its_first_frame():
    assert arrival.propose(_series(at=120)) == 120


def test_a_hole_forming_over_frames_is_proposed_where_it_is_mostly_formed():
    d = _series(at=120)
    d[118:121] = [2.0, 4.0, 7.0]   # smear, half-formed, formed
    assert arrival.propose(d) == 120


def test_a_passing_flash_is_not_the_hole():
    d = _series(at=150)
    d[60:62] = 20.0   # a dust puff or a shadow, gone the next frame
    assert arrival.propose(d) == 150


def test_slow_drift_does_not_hide_the_step():
    d = _series(at=100) + np.linspace(0, 4, 200)   # exposure creeping up
    assert arrival.propose(d) == 100


def test_a_later_larger_change_at_the_hole_does_not_move_its_arrival():
    # CamB _102250 truth #3: formed at frame 41, faded, then changed more at ~230.
    d = _series(n=400, at=40, before=3, after=60)
    d[120:220] = np.linspace(60, 18, 100)
    d[220:] = 90
    assert arrival.propose(d) == 40


def test_the_file_holds_one_line_per_truth_line_that_regression_reads(tmp_path):
    from tools import regression
    arrival.write(tmp_path, [412, None, 77])
    assert (tmp_path / regression.ARRIVAL_NAME).read_text() == (
        "412 proposed\n- proposed\n77 proposed\n")
    assert regression.arrival_frames(tmp_path) == [412, None, 77]


def test_a_flash_in_the_last_frames_is_not_the_hole():
    d = _series(at=120)
    d[-3:] = 50.0   # the window ends on a flash: no full second after it
    assert arrival.propose(d) == 120


def test_a_rerun_keeps_reviewed_lines(tmp_path):
    from tools import regression
    (tmp_path / regression.ARRIVAL_NAME).write_text(
        "412 confirmed\n90 proposed\n779 corrected\n")
    arrival.write(tmp_path, [412, 91, 787])
    assert (tmp_path / regression.ARRIVAL_NAME).read_text() == (
        "412 confirmed\n91 proposed\n779 corrected\n")


def test_a_rerun_refuses_when_the_truth_changed_under_reviewed_lines(tmp_path):
    import pytest
    from tools import regression
    path = tmp_path / regression.ARRIVAL_NAME
    path.write_text("412 confirmed\n")
    with pytest.raises(SystemExit):
        arrival.write(tmp_path, [412, 91])
    assert path.read_text() == "412 confirmed\n"
