"""Checks for the detector probe. No model, no video, no torch.

The probe is only worth running if it gives the known answer where the answer
is known, so these pin the arithmetic it is read through: what counts as a
frame that got a look, and what counts as a detection of THIS Bullet Hole.
"""
import numpy as np
import pytest

from detection import new_bullet_holes as nbh
from tools import manifest, probe

HOLE = (100.0, 100.0)
RADIUS = 5.0


def _look(index, *centres):
    """A registered frame holding a detection at each centre."""
    boxes = [[x, y, 4.0, 4.0] for x, y in centres]
    return nbh.Look(index, object(), None, np.array(boxes, np.float32).reshape(-1, 4))


def _lost(index):
    return nbh.Look(index, None, None, None)


def _rate(looks, positions=(HOLE,)):
    return [r.rate for r in probe.detection_rates(looks, positions, RADIUS)]


def test_a_hole_detected_in_every_frame_reports_one():
    assert _rate([_look(i, HOLE) for i in range(10)]) == [1.0]


def test_a_hole_detected_in_no_frame_reports_zero():
    assert _rate([_look(i) for i in range(10)]) == [0.0]


def test_a_lost_frame_is_excluded_rather_than_counted_as_unseen():
    """The rule persistence already follows: no look, no evidence either way."""
    looks = [_look(0, HOLE), _lost(1), _lost(2), _look(3, HOLE)]
    [r] = probe.detection_rates(looks, [HOLE], RADIUS)
    assert r.rate == 1.0 and r.looked == 2


def test_the_radius_is_inclusive_and_nothing_beyond_it_counts():
    on_edge = _look(0, (HOLE[0] + RADIUS, HOLE[1]))
    just_outside = _look(1, (HOLE[0] + RADIUS + 0.01, HOLE[1]))
    assert _rate([on_edge, just_outside]) == [0.5]


def test_two_holes_get_independent_rates():
    """A detection near one Bullet Hole does not credit the other."""
    other = (140.0, 100.0)
    looks = [_look(0, HOLE), _look(1, HOLE), _look(2, HOLE, other), _look(3, HOLE)]
    assert _rate(looks, [HOLE, other]) == [1.0, 0.25]


def test_one_detection_between_two_close_holes_credits_only_one():
    """One-to-one, as `evaluate.match` scores a run: one mark seen, not two."""
    other = (HOLE[0] + RADIUS, HOLE[1])
    between = (HOLE[0] + RADIUS / 2, HOLE[1])
    assert sum(_rate([_look(0, between)], [HOLE, other])) == 1.0


def test_two_detections_on_one_hole_count_its_frame_once():
    assert _rate([_look(0, HOLE, (101.0, 100.0)), _look(1)]) == [0.5]


def test_no_registered_frame_is_no_rate_rather_than_zero():
    """Zero would claim the detector missed a hole nothing looked at."""
    [r] = probe.detection_rates([_lost(0), _lost(1)], [HOLE], RADIUS)
    assert r.rate is None and r.looked == 0


def test_the_longest_blind_run_spans_registered_frames_only():
    """The CamB finding is a run, not a rate: seen, then blind for 21 seconds.

    A lost frame inside the run neither breaks it nor lengthens its count.
    """
    looks = ([_look(0, HOLE), _look(1, HOLE), _look(2), _lost(3), _look(4),
              _look(5), _look(6, HOLE), _look(7)])
    [r] = probe.detection_rates(looks, [HOLE], RADIUS)
    assert r.blind == probe.BlindRun(first=2, last=5, frames=3)
    assert (r.first, r.last) == (0, 6)


def test_a_bullet_hole_always_seen_has_no_blind_run():
    [r] = probe.detection_rates([_look(0, HOLE), _look(1, HOLE)], [HOLE], RADIUS)
    assert r.blind is None


def test_an_explicit_position_is_template_x_y():
    assert probe.parse_point("512.5,-3") == (512.5, -3.0)


def test_a_malformed_position_is_refused():
    import argparse
    for bad in ("512.5", "1,2,3", "x,y"):
        with pytest.raises(argparse.ArgumentTypeError):
            probe.parse_point(bad)


def _sealed(tmp_path, monkeypatch):
    """A stand-in sealed recording, the `where` that allocates it, and the log
    path, not yet written. The commit is pinned so no git runs."""
    monkeypatch.setattr(manifest, "git_commit", lambda: "abc1234")
    video, log = tmp_path / "clip.mkv", tmp_path / "sealed_runs.log"
    video.write_bytes(b"frames")
    entries = {manifest.content_hash(str(video)): {"role": manifest.SEALED}}
    return str(video), dict(entries=entries, log_path=str(log)), log


def test_a_sealed_final_run_over_two_models_is_one_look(tmp_path, monkeypatch):
    """Gated once per model, the second gate found the first look in the log
    and refused: the look spent, nothing measured (#139)."""
    video, where, log = _sealed(tmp_path, monkeypatch)

    assert probe.gate(video, True, ["a/best.pt", "b/best.pt"], **where)["role"] == manifest.SEALED
    [line] = log.read_text().splitlines()
    assert "a/best.pt" in line and "b/best.pt" in line and "tool=probe.py" in line


def test_probe_refuses_a_sealed_recording_without_the_flag(tmp_path, monkeypatch):
    video, where, log = _sealed(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="--final-run"):
        probe.gate(video, False, ["a/best.pt"], **where)
    assert not log.exists()


def test_probe_refuses_a_measured_recording_flag_or_not(tmp_path, monkeypatch):
    video, where, log = _sealed(tmp_path, monkeypatch)
    probe.gate(video, True, ["a/best.pt"], **where)
    before = log.read_text()
    for final_run in (True, False):
        with pytest.raises(SystemExit, match="measured"):
            probe.gate(video, final_run, ["b/best.pt"], **where)
    assert log.read_text() == before
