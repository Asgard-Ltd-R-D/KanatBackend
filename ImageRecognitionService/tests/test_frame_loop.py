"""Checks for the shared registered-frame loop. No model, no video, no torch.

The loop exists so the pipeline and the detector probe look at the same image.
What is testable without a video file is the bookkeeping the probe depends on:
which frames got a look, and which only appeared to.
"""
import itertools
import types

import numpy as np

from detection import new_bullet_holes as nbh


class _FakeView:
    """Board space, minus the geometry. Rectifying is the identity here, and
    the canvas never grew past the margin canvas."""
    canvas_size = (64, 64)
    match_radius = 3.0
    grew = False

    def rectify(self, frame):
        return frame

    def exposed_bands(self, context):
        return []


class _GrownView(_FakeView):
    """A canvas grown 16 px below the margin canvas: `rectify` is the grown
    canvas, `rectify_inner` the margin canvas, marked so the model can tell."""
    grew = True
    canvas_size = (64, 80)
    inner = types.SimpleNamespace(offset=(0, 0), size=(64, 64))

    def rectify(self, frame):
        return np.full((80, 64, 3), 7, np.uint8)

    def rectify_inner(self, frame):
        return np.full((64, 64, 3), 1, np.uint8)

    def exposed_bands(self, context):
        return [nbh.board.Band((0, 64 - context, 64, 80), (0, 64, 64, 80))]

    def in_inner(self, points):
        return np.asarray(points)[:, 1] <= 64


class _FakeCap:
    """A file holding `n` frames after the one Board space was built from."""
    def __init__(self, n):
        self.left, self.released = n, False

    def read(self):
        if self.left <= 0:
            return False, None
        self.left -= 1
        return True, np.zeros((8, 8, 3), np.uint8)

    def release(self):
        self.released = True


class _FakeModel:
    """One box per frame, wherever it is asked to look."""
    names = {0: "bullet_hole"}

    def predict(self, image, imgsz, conf, verbose=False, classes=None):
        box = types.SimpleNamespace(xyxy=[[10.0, 10.0, 20.0, 20.0]])
        return [types.SimpleNamespace(boxes=[box])]


def _loop(monkeypatch, registers, frames=10, below=lambda i: 0.0):
    """A loop over `frames` frames; `registers(index)` says which ones register,
    and `below(index)` how far that frame's view runs past the canvas bottom,
    in Board px against a 100 px Target span — None for an unmeasurable view."""
    seen = iter(range(1, frames + 1))
    measured = itertools.count()   # the baseline in __init__, then each look
    edges = dict.fromkeys(("left", "right", "above"), 0.0)
    def uncovered(view, size):
        reach = below(next(measured))
        return None if reach is None else (0.0, {**edges, "below": reach})
    monkeypatch.setattr(nbh.board, "uncovered_view", uncovered)
    monkeypatch.setattr(nbh.board, "target_span", lambda view: 100.0)
    monkeypatch.setattr(nbh.board, "track_view",
                        lambda frame, last: (
                            _FakeView() if registers(next(seen)) else None, 0.9))
    return nbh.RegisteredFrames(_FakeCap(frames), _FakeModel(), _FakeView(),
                                np.zeros((8, 8, 3), np.uint8), imgsz=64, conf=0.02,
                                fps=25.0, start=10.0)


def test_a_lost_frame_is_not_a_frame_that_saw_nothing(monkeypatch):
    """The whole point of the Look: the probe must not score a lost frame as a miss."""
    loop = _loop(monkeypatch, lambda i: i != 3)
    looks = list(loop.looks(5))

    lost = [l for l in looks if not l.registered]
    assert len(lost) == 1 and lost[0].index == 3
    assert lost[0].detections is None          # not an empty array
    assert all(len(l.detections) == 1 for l in looks if l.registered)
    assert (loop.processed, loop.lost) == (5, 1)


def test_indices_keep_counting_across_a_lost_frame(monkeypatch):
    """Frame numbers are positions in the clip, not positions in the output."""
    loop = _loop(monkeypatch, lambda i: i not in (2, 3))
    assert [l.index for l in loop.looks(6)] == [0, 1, 2, 3, 4, 5]


def test_the_first_frame_is_the_one_board_space_was_built_from(monkeypatch):
    """It is already read and already registered, and still yielded like any other."""
    loop = _loop(monkeypatch, lambda i: True)
    first = next(loop.looks(4))
    assert first.index == 0 and first.view is loop.view


def test_a_short_file_stops_early_rather_than_padding(monkeypatch):
    """`processed` is what confirmation is measured against, so it must be real."""
    loop = _loop(monkeypatch, lambda i: True, frames=2)
    assert len(list(loop.looks(50))) == 3      # the baseline frame plus two reads
    assert loop.processed == 3


def test_the_capture_is_released_when_iteration_ends(monkeypatch):
    loop = _loop(monkeypatch, lambda i: True, frames=2)
    list(loop.looks(50))
    assert loop.cap.released


def test_frames_until_counts_from_the_start_timestamp(monkeypatch):
    loop = _loop(monkeypatch, lambda i: True)
    assert loop.frames_until(14.0) == 100      # 4s at 25 fps


def test_detection_asks_for_bullet_holes_only_whatever_their_id():
    """The v2.0 checkpoint also emits Board and Target, and bullet_hole is id 1."""
    asked = {}

    class ThreeClass(_FakeModel):
        names = {0: "board", 1: "bullet_hole", 2: "target"}

        def predict(self, image, imgsz, conf, verbose=False, classes=None):
            asked["classes"] = classes
            return super().predict(image, imgsz, conf, verbose, classes)

    nbh._detect(ThreeClass(), None, 64, 0.02)
    assert asked["classes"] == [1]


def test_a_model_without_bullet_holes_is_refused():
    import pytest

    class NoHoles(_FakeModel):
        names = {0: "target"}

    with pytest.raises(SystemExit):
        nbh._detect(NoHoles(), None, 64, 0.02)


def test_a_view_moving_further_off_the_canvas_is_reported_once(monkeypatch, capsys):
    """The baseline's view is only the first: a camera that later swings past
    the canvas uncovers Board no run searches (#41)."""
    loop = _loop(monkeypatch, lambda i: True, frames=4,
                 below=lambda i: [0.0, 0.0, 0.0, 40.0, 20.0, 0.0][i])
    list(loop.looks(5))
    out = capsys.readouterr().out
    assert out.count("further off the canvas than the baseline did") == 1
    assert "0.40 below" in out


def test_a_view_that_stays_within_the_baseline_says_nothing(monkeypatch, capsys):
    loop = _loop(monkeypatch, lambda i: True, frames=3)
    list(loop.looks(4))
    assert "[WARN]" not in capsys.readouterr().out


def test_any_growth_past_rounding_is_reported(monkeypatch, capsys):
    """A pixel more than the baseline showed is Board no run searched, however
    it prints; only the sub-pixel rounding floor is let through."""
    loop = _loop(monkeypatch, lambda i: True, frames=2,
                 below=lambda i: [30.0, 30.0, 31.0, 30.0][i])
    list(loop.looks(3))
    assert "further off the canvas than the baseline did" in capsys.readouterr().out


def test_a_later_view_that_cannot_be_measured_is_reported(monkeypatch, capsys):
    """The baseline measured fine, so its line said nothing is unknown; a later
    frame past the Board plane's horizon still has to say so."""
    loop = _loop(monkeypatch, lambda i: True, frames=3,
                 below=lambda i: [0.0, 0.0, None, 0.0, 0.0][i])
    list(loop.looks(4))
    assert "[WARN] 1 registered frame(s)' view did not map" in capsys.readouterr().out


class _RecordingModel(_FakeModel):
    """Answers per image: a box at (15, 15) on the margin canvas, one at
    (20, 8) band px (canvas y 40) inside the band's context, and one at
    (30, 40) band px (canvas y 72, past the margin canvas) in the band."""
    names = {0: "bullet_hole"}

    def __init__(self):
        self.calls = []

    def predict(self, image, imgsz, conf, verbose=False, classes=None):
        self.calls.append((image.shape[:2], int(image[0, 0, 0]), imgsz))
        if image[0, 0, 0] == 1:
            boxes = [[10.0, 10.0, 20.0, 20.0]]
        else:
            boxes = [[18.0, 6.0, 22.0, 10.0], [28.0, 38.0, 32.0, 42.0]]
        return [types.SimpleNamespace(boxes=[types.SimpleNamespace(xyxy=[b]) for b in boxes])]


def test_a_canvas_that_did_not_grow_is_shown_to_the_detector_once(monkeypatch):
    """No Board past the margin canvas: one inference on the canvas, as before #46."""
    model = _RecordingModel()
    loop = _loop(monkeypatch, lambda i: True, frames=1)
    loop.model = model
    looks = list(loop.looks(2))
    assert len(model.calls) == 2 and all(imgsz == 64 for _, _, imgsz in model.calls)
    assert looks[0].inner is looks[0].canvas


def test_a_grown_canvas_is_searched_as_the_margin_canvas_plus_its_bands(monkeypatch):
    """A on the margin canvas at the loop's imgsz; B on each band at its own;
    B keeps only what lies past the margin canvas, in grown-canvas px."""
    model = _RecordingModel()
    loop = _loop(monkeypatch, lambda i: True, frames=0)
    loop.view = loop.last = _GrownView()
    loop._base = np.zeros((8, 8, 3), np.uint8)
    loop.model, loop.bands = model, loop.view.exposed_bands(nbh.BAND_CONTEXT_PX)
    look = next(loop.looks(1))
    assert model.calls == [((64, 64), 1, 64), ((48, 64), 7, 64)]
    assert look.detections[:, :2].tolist() == [[15.0, 15.0], [30.0, 72.0]]
    assert look.inner.shape == (64, 64, 3) and look.canvas.shape == (80, 64, 3)
