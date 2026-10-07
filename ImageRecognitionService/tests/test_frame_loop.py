"""Checks for the shared registered-frame loop. No model, no video, no torch.

The loop exists so the pipeline and the detector probe look at the same image.
What is testable without a video file is the bookkeeping the probe depends on:
which frames got a look, and which only appeared to.
"""
import itertools
import math
import os
import re
import signal
import socket
import sys
import time
import types

import numpy as np
import pytest

from detection import new_bullet_holes as nbh


class _FakeView:
    """Board space, minus the geometry. Rectifying is the identity here, and
    the canvas never grew past the margin canvas."""
    canvas_size = (64, 64)
    match_radius = 3.0
    grew = False
    targets = [None]
    board_scale = 1.0
    inner = types.SimpleNamespace(offset=(0, 0), size=(64, 64))

    def rectify(self, frame):
        return frame

    def exposed_bands(self, context):
        return []

    def in_inner(self, points):
        return np.ones(len(points), bool)

    def assign(self, pos):
        return None   # every Bullet Hole is a Miss: no Target geometry here


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
    """A file holding `n` frames after the one Board space was built from.
    Each frame's pixels are its index in the clip, so a fake can tell which
    frame it was handed; `grabbed` is the indices skipped without decoding."""
    def __init__(self, n):
        self.n, self.at, self.released, self.grabbed = n, 0, False, []

    def grab(self):
        if self.at >= self.n:
            return False
        self.at += 1
        self.grabbed.append(self.at)
        return True

    def read(self):
        if self.at >= self.n:
            return False, None
        self.at += 1
        return True, np.full((8, 8, 3), self.at, np.int64)

    def release(self):
        self.released = True

    def get(self, prop):
        return 25.0

    def set(self, prop, value):
        pass


class _FakeModel:
    """One box per frame, wherever it is asked to look."""
    names = {0: "bullet_hole"}

    def predict(self, image, imgsz, conf, verbose=False, classes=None):
        box = types.SimpleNamespace(xyxy=[[10.0, 10.0, 20.0, 20.0]])
        return [types.SimpleNamespace(boxes=[box])]


def _loop(monkeypatch, registers, frames=10, below=lambda i: 0.0,
          reanchors=lambda i: False, correlation=lambda i: 0.9,
          disagreement=lambda i: 0.0, cap=None):
    """A loop over `frames` frames; `registers(index)` says which ones register
    when tracked, `reanchors(index)` which when re-anchored (#80), and
    `below(index)` how far that frame's view runs past the canvas bottom,
    in Board px against a 100 px Target span — None for an unmeasurable view.
    A fit converges at `correlation(index)`, and an independent silhouette fit
    disagrees with it by `disagreement(index)` Board px (#110).

    `loop.calls` records `(how, index, last)` for each frame read, where `how`
    is "track" or "reanchor" and `last` is the view it was handed;
    `loop.silhouetted` the indices whose fit was checked against the silhouette."""
    calls, checked = [], []
    def fit(how, succeeds):
        def call(frame, *args):
            index, last = int(frame[0, 0, 0]), args[-1]
            calls.append((how, index, last))
            if not succeeds(index):
                return None, None
            view = _FakeView()
            view.index = index
            # A re-anchor only ever returns a fit at or above its floor.
            floor = nbh.board.REANCHOR_MIN_CORRELATION if how == "reanchor" else 0.0
            return view, max(floor, correlation(index))
        return call
    def silhouette(frame, template_mask, view):
        checked.append(view.index)
        return disagreement(view.index)
    monkeypatch.setattr(nbh.board, "silhouette_disagreement", silhouette)
    measured = itertools.count()   # the baseline in __init__, then each look
    edges = dict.fromkeys(("left", "right", "above"), 0.0)
    def uncovered(view, size):
        reach = below(next(measured))
        return None if reach is None else (0.0, {**edges, "below": reach})
    monkeypatch.setattr(nbh.board, "uncovered_view", uncovered)
    monkeypatch.setattr(nbh.board, "target_span", lambda view: 100.0)
    monkeypatch.setattr(nbh.board, "track_view", fit("track", registers))
    monkeypatch.setattr(nbh.board, "reanchor_view", fit("reanchor", reanchors))
    loop = nbh.RegisteredFrames(cap or _FakeCap(frames), _FakeModel(), _FakeView(),
                                np.zeros((8, 8, 3), np.uint8), imgsz=64, conf=0.02,
                                fps=25.0, start=10.0, template_mask=np.zeros((8, 8), np.uint8))
    loop.calls, loop.silhouetted = calls, checked
    return loop


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


def test_opening_reports_how_long_building_board_space_took(monkeypatch, capsys):
    """Wall time from opening the source to Board space built, printed once (#79).
    The value is the machine's, so only that it is reported is checked."""
    monkeypatch.setitem(sys.modules, "ultralytics",
                        types.SimpleNamespace(YOLO=lambda path: _FakeModel()))
    monkeypatch.setattr(nbh.cv2, "imread", lambda path: np.zeros((8, 8, 3), np.uint8))
    monkeypatch.setattr(nbh.cv2, "VideoCapture", lambda video: _FakeCap(1))
    monkeypatch.setattr(nbh.board, "find_targets", lambda image, min_area=None: ([None], None))
    monkeypatch.setattr(nbh.board, "template_contour", lambda mask: None)
    monkeypatch.setattr(nbh.board, "contour_span", lambda contour: 100.0)
    monkeypatch.setattr(nbh.board, "net_scale", lambda *args: 1.0)
    monkeypatch.setattr(nbh.board, "build_view", lambda frame, mask: (_FakeView(), 0.95))
    monkeypatch.setattr(nbh.board, "uncovered_view",
                        lambda view, size: (0.0, dict.fromkeys(
                            ("left", "right", "above", "below"), 0.0)))
    nbh.RegisteredFrames.open("clip.mkv", 10.0, "model.pt")
    assert capsys.readouterr().out.count("[REGISTRATION] Board space built in ") == 1


# --- re-anchoring after the Board is lost (#80) ------------------------------

N = nbh.REANCHOR_AFTER_LOST


def _reanchored(loop):
    return [index for how, index, _ in loop.calls if how == "reanchor"]


def test_one_lost_frame_short_of_the_trigger_does_not_re_anchor(monkeypatch):
    loop = _loop(monkeypatch, lambda i: i > N - 1, frames=N + 5)
    list(loop.looks(N + 6))
    assert _reanchored(loop) == []


def test_the_frame_after_a_full_trigger_of_lost_frames_is_re_anchored(monkeypatch):
    """Frames 1..N are lost; frame N+1 is re-anchored instead of tracked."""
    loop = _loop(monkeypatch, lambda i: False, frames=N + 5)
    list(loop.looks(N + 6))
    assert _reanchored(loop) == [N + 1]


def test_after_a_re_anchor_later_frames_track_from_the_re_anchored_view(monkeypatch):
    loop = _loop(monkeypatch, lambda i: i > N + 1, frames=N + 4,
                 reanchors=lambda i: True)
    looks = list(loop.looks(N + 5))
    recovered = looks[N + 1]
    assert recovered.registered and recovered.index == N + 1
    after = [last for how, index, last in loop.calls if index == N + 2]
    assert after == [recovered.view]
    assert all(l.registered for l in looks[N + 1:])


def test_a_re_anchor_starts_from_the_last_registered_view(monkeypatch):
    """Board space and the anchor come from it; nothing is rebuilt."""
    loop = _loop(monkeypatch, lambda i: False, frames=N + 1)
    list(loop.looks(N + 2))
    assert [last for how, _, last in loop.calls if how == "reanchor"] == [loop.view]


def test_a_failed_re_anchor_stays_lost_and_waits_a_full_interval(monkeypatch):
    loop = _loop(monkeypatch, lambda i: False, frames=3 * N + 5)
    looks = list(loop.looks(3 * N + 6))
    assert _reanchored(loop) == [N + 1, 2 * N + 1, 3 * N + 1]
    assert not any(l.registered for l in looks[1:])
    assert [l.index for l in looks] == list(range(3 * N + 6))
    assert all(l.detections is None for l in looks[1:])


def test_a_registered_frame_resets_the_count(monkeypatch):
    """Only consecutive lost frames trigger: N lost in two runs is not N in a row."""
    loop = _loop(monkeypatch, lambda i: i == N // 2, frames=N + 5)
    list(loop.looks(N + 6))
    assert _reanchored(loop) == []


def test_each_re_anchor_is_reported_and_counted_at_the_end(monkeypatch, capsys):
    loop = _loop(monkeypatch, lambda i: False, frames=2 * N + 2,
                 reanchors=lambda i: i == 2 * N + 1)
    list(loop.looks(2 * N + 3))
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if "[REGISTRATION] re-anchor at" in l]
    assert len(lines) == 2
    assert f"frame {N + 1}" in lines[0] and f"after {N} lost" in lines[0]
    assert "failed" in lines[0]
    assert f"frame {2 * N + 1}" in lines[1] and f"after {2 * N} lost" in lines[1]
    assert "registered" in lines[1]
    assert "[REGISTRATION] 2 re-anchor attempt(s): 1 registered, 1 failed" in out


def test_a_run_that_never_lost_the_board_reports_no_re_anchor(monkeypatch, capsys):
    loop = _loop(monkeypatch, lambda i: True, frames=3)
    list(loop.looks(4))
    assert "[REGISTRATION] 0 re-anchor attempt(s)" in capsys.readouterr().out
    assert _reanchored(loop) == []


def _rendering(monkeypatch, frames):
    """`_render` over a `frames`-frame clip. Returns `(named, drawn, written)`:
    `named(name)` is a view that logs `name` to `drawn` when it rectifies, and
    `written` counts the frames the output video got."""
    drawn, written = [], []

    class _Named(_FakeView):
        targets = []

        def __init__(self, name):
            self.name = name

        def rectify(self, frame):
            drawn.append(self.name)
            return np.zeros((64, 64, 3), np.uint8)

    class _Writer:
        def write(self, image):
            written.append(1)

        def release(self):
            pass

    monkeypatch.setattr(nbh.cv2, "VideoCapture", lambda video: _FakeCap(frames))
    monkeypatch.setattr(nbh.cv2, "VideoWriter", lambda *args: _Writer())
    monkeypatch.setattr(nbh.board, "track_view",
                        lambda *args: (_ for _ in ()).throw(AssertionError("re-registered")))
    return _Named, drawn, written


def test_render_draws_each_frame_with_the_view_detection_used(monkeypatch):
    """`_render` registers nothing (#80): a re-anchored view is drawn from its
    frame on, and a lost frame keeps the last view before it."""
    named, drawn, _ = _rendering(monkeypatch, 5)
    views = {0: named("base"), 1: named("base"), 3: named("re-anchored")}
    nbh._render("clip.mp4", 0.0, 5, 25.0, views, [], [], "out.mp4")
    assert drawn == ["base", "base", "base", "re-anchored", "re-anchored"]


def test_render_leaves_out_the_frames_a_stride_skipped(monkeypatch):
    """A gap has no registration of its own; drawn with the last look's, it
    would show stale geometry (#81 review). Only looked-at frames are written."""
    named, drawn, written = _rendering(monkeypatch, 20)
    views = {i: named(i) for i in (0, 1, 2, 3, 4, 13)}
    nbh._render("clip.mp4", 0.0, 20, 25.0, views, [], [], "out.mp4",
                stride=13, baseline_frames=5)
    assert drawn == [0, 1, 2, 3, 4, 13] and len(written) == 6


def test_an_interval_shorter_than_a_frame_still_renders(monkeypatch):
    """`--end` at `--start` reads no frame; `--out` gets Board space's own view
    rather than a KeyError."""
    loop = _loop(monkeypatch, lambda i: True)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    rendered = []
    monkeypatch.setattr(nbh, "_render", lambda video, start, n, fps, views, *rest:
                        rendered.append((n, views)))
    nbh.process("clip.mp4", 10.0, 10.0, "model.pt", out_video="out.mp4")
    assert rendered == [(0, {0: loop.view})]


def test_rendering_gets_the_view_of_every_frame_read(monkeypatch):
    """Views are kept only for `--out` (#80); when they are, none is missing."""
    loop = _loop(monkeypatch, lambda i: True)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    rendered = []
    monkeypatch.setattr(nbh, "_render", lambda video, start, n, fps, views, *rest:
                        rendered.append(sorted(views)))
    nbh.process("clip.mp4", 10.0, 10.4, "model.pt", out_video="out.mp4")
    assert rendered == [list(range(10))]


# --- a converged fit that is grossly wrong (#110) ----------------------------

GROSS = nbh.GROSS_DISAGREEMENT_PX


def test_a_fit_converging_above_the_floor_is_not_checked(monkeypatch):
    """The check costs ~0.5 s a frame; a fit the re-anchor floor would accept
    is not paid for (#110)."""
    loop = _loop(monkeypatch, lambda i: True, frames=4,
                 correlation=lambda i: nbh.board.REANCHOR_MIN_CORRELATION,
                 disagreement=lambda i: 10 * GROSS)
    looks = list(loop.looks(5))
    assert loop.silhouetted == [] and all(l.registered for l in looks)


def test_a_grossly_wrong_fit_is_lost_and_feeds_the_re_anchor(monkeypatch):
    """Frames 1..N converge on the wrong scene: each is lost, the count runs
    on, and frame N+1 is re-anchored from the last right view (#110, #80)."""
    loop = _loop(monkeypatch, lambda i: True, frames=N + 3,
                 correlation=lambda i: 0.2, disagreement=lambda i: GROSS)
    looks = list(loop.looks(N + 4))
    assert not any(l.registered for l in looks[1:N + 1])
    assert all(l.detections is None for l in looks[1:N + 1])
    assert loop.lost == N + 3   # every frame after the baseline: none recovers
    assert _reanchored(loop) == [N + 1] and loop.reanchors == 1
    assert all(last is loop.view for how, i, last in loop.calls if i <= N + 1)


def test_a_moderate_disagreement_keeps_the_frame_and_warns_once(monkeypatch, capsys):
    """Below the gross bound nothing is rejected; the run says how many of the
    frames it checked disagreed, and that only those were checked (#110)."""
    loop = _loop(monkeypatch, lambda i: True, frames=5,
                 correlation=lambda i: 0.5 if i in (2, 3, 4) else 0.95,
                 disagreement=lambda i: GROSS - 1 if i in (2, 3) else 0.0)
    looks = list(loop.looks(6))
    assert all(l.registered for l in looks) and loop.lost == 0
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if "silhouette" in l and "[WARN]" in l]
    assert len(lines) == 1
    assert "2 of 3" in lines[0]


def test_a_check_with_no_verdict_keeps_the_frame(monkeypatch, capsys):
    """A silhouette fit that fails says nothing about the tracked one."""
    loop = _loop(monkeypatch, lambda i: True, frames=3,
                 correlation=lambda i: 0.2, disagreement=lambda i: None)
    looks = list(loop.looks(4))
    assert all(l.registered for l in looks) and loop.lost == 0
    assert "0 of 3 converged fit(s) checked" in capsys.readouterr().out


def test_the_pipeline_hands_persistence_the_frames_it_lost(monkeypatch):
    """The #110 floor counts frames tried and lost, so `process` must say which
    were lost; a frame it never read (a stride gap, #81) is not among them."""
    loop = _loop(monkeypatch, lambda i: i not in (7, 8))
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    handed = {}
    def track(per_frame, n_frames, match_px, lost=()):
        handed["lost"] = list(lost)
        return []
    monkeypatch.setattr(nbh, "track_new_bullet_holes", track)
    nbh.process("clip.mp4", 10.0, 10.4, "model.pt")
    assert handed["lost"] == [7, 8]


# --- a stride: look at every Nth frame (#81) ---------------------------------


def test_a_stride_looks_at_the_first_frames_then_its_multiples_past_them(monkeypatch):
    """The baseline's frames 0..B-1 are all looked at whatever the stride; past
    them, only multiples of the stride at or after B (#81)."""
    for stride, expected in [(13, [0, 1, 2, 3, 4, 13, 26, 39, 52]),
                             (2, [0, 1, 2, 3, 4, 6, 8, 10]),
                             (1, list(range(11)))]:
        loop = _loop(monkeypatch, lambda i: True, frames=60)
        last = expected[-1] + 1
        assert [l.index for l in loop.looks(last, stride, 5)] == expected


def test_frames_a_stride_skips_are_neither_registered_nor_yielded(monkeypatch):
    """A skipped frame is a gap, not a lost frame: never decoded, never fitted."""
    loop = _loop(monkeypatch, lambda i: True, frames=30)
    looks = list(loop.looks(30, 13, 5))
    assert [index for _, index, _ in loop.calls] == [1, 2, 3, 4, 13, 26]
    assert all(l.registered for l in looks)
    assert loop.cap.grabbed == [i for i in range(5, 30) if i % 13]
    assert (loop.processed, loop.lost) == (30, 0)


def test_a_stride_stops_at_the_end_of_the_file(monkeypatch):
    """A failed grab is the end of the file too, so `processed` stays real."""
    loop = _loop(monkeypatch, lambda i: True, frames=20)
    assert [l.index for l in loop.looks(50, 13, 5)] == [0, 1, 2, 3, 4, 13]
    assert loop.processed == 21


class _SeenOn(_FakeModel):
    """A Bullet Hole at (15, 15) on the frames `on(index)` says. The frame's
    pixels are its index (see `_FakeCap`), which is why they are int64."""
    def __init__(self, on):
        self.on = on

    def predict(self, image, imgsz, conf, verbose=False, classes=None):
        return super().predict(image, imgsz, conf) if self.on(int(image[0, 0, 0])) \
            else [types.SimpleNamespace(boxes=[])]


def _strided_run(monkeypatch, n_frames, on=lambda i: i >= 6):
    """`process` at stride 13 over `n_frames`; half a frame on `--end` keeps
    `frames_until` clear of float truncation."""
    loop = _loop(monkeypatch, lambda i: True, frames=100)
    loop.model = _SeenOn(on)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    monkeypatch.setattr(nbh.board, "changed_regions", lambda a, b: np.zeros((8, 8), bool))
    return nbh.process("clip.mp4", 10.0, 10.0 + (n_frames + 0.5) / 25, "model.pt",
                       require_change_evidence=False, stride=13)


def test_at_stride_13_a_bullet_hole_from_frame_6_is_new_and_first_seen_on_13(monkeypatch):
    """Not in the baseline (frames 0-4), first looked at on 13, confirmed once
    its window has elapsed (#81)."""
    run = _strided_run(monkeypatch, 13 + nbh.PERSIST_FRAMES)
    assert len(run.baseline) == 0
    assert [h["first_frame"] for h in run.holes] == [13]
    assert run.holes[0]["seen"] == [13, 26, 39, 52]


def test_at_stride_13_a_bullet_hole_is_withheld_until_its_window_elapses(monkeypatch):
    """One frame short of its window, it is unconfirmable, not rejected."""
    run = _strided_run(monkeypatch, 13 + nbh.PERSIST_FRAMES - 1)
    assert run.holes == []


def test_at_stride_13_a_detection_on_one_sampled_frame_is_dropped(monkeypatch):
    """Seen on 13 alone of the window's looks at 13, 26, 39, 52: a flicker."""
    run = _strided_run(monkeypatch, 13 + nbh.PERSIST_FRAMES, on=lambda i: i == 13)
    assert run.holes == []


def test_the_report_states_the_stride(monkeypatch, capsys):
    """A stride-sampled result is only comparable at the same stride (#81)."""
    _strided_run(monkeypatch, 25)
    assert "[INFO] stride 13:" in capsys.readouterr().out


def test_a_stride_leaving_one_look_a_window_is_refused():
    """At a stride of the persistence window or more, a window holds one look,
    and any single sighting would confirm at 1/1 (#81 review)."""
    import argparse
    import pytest
    parser = argparse.ArgumentParser()
    nbh.add_stride_flag(parser)
    assert parser.parse_args(["--stride", str(nbh.PERSIST_FRAMES - 1)]).stride == \
        nbh.PERSIST_FRAMES - 1
    for refused in ("0", str(nbh.PERSIST_FRAMES)):
        with pytest.raises(SystemExit):
            parser.parse_args(["--stride", refused])


# --- live from an RTSP URL (#83) ---------------------------------------------


class _FakeStream:
    """A live source: a frame every `interval` seconds, `n` of them, or for as
    long as it is read when `n` is None. Pixels are the frame's index, as in
    `_FakeCap`. Read through `grab` and `retrieve`, as the reader thread does."""
    def __init__(self, n=None, interval=0.0):
        self.n, self.interval, self.at, self.released = n, interval, 0, False

    def grab(self):
        if self.n is not None and self.at >= self.n:
            return False
        time.sleep(self.interval)
        self.at += 1
        return True

    def retrieve(self):
        return True, np.full((8, 8, 3), self.at, np.int64)

    def release(self):
        self.released = True


class _Slow(_FakeModel):
    """`_FakeModel`, taking `seconds` a look."""
    def __init__(self, seconds):
        self.seconds = seconds

    def predict(self, *args, **kwargs):
        time.sleep(self.seconds)
        return super().predict(*args, **kwargs)


def _live(monkeypatch, stream, reopen=None):
    """A loop over `stream`, reopened by `reopen` after a drop. By default a
    stream that runs out is down for good: its first reopen stops the run, as
    an operator would."""
    monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.01)
    def stop():
        live.stop()
        return _FakeStream(n=0)
    live = nbh._Stream(stream, time.time(), reopen or stop)
    return _loop(monkeypatch, lambda i: True, cap=live)


def test_a_stream_is_looked_at_on_the_stride_and_frames_it_is_too_late_for_are_dropped(
        monkeypatch):
    """30 ms a look against a due frame every 3 ms: each look takes the newest
    due frame, and the ones it was too late for are counted, not queued. The
    baseline's frames are consecutive however slow their looks (#83)."""
    loop = _live(monkeypatch, _FakeStream(n=200, interval=0.001))
    loop.model = _Slow(0.03)
    indices = [l.index for l in loop.looks(math.inf, stride=3, baseline_frames=5)]
    assert indices[:5] == [0, 1, 2, 3, 4]
    past = indices[5:]
    assert past[0] == 6   # nothing dropped until the baseline was built
    assert past == sorted(set(past)) and all(i % 3 == 0 for i in past)
    assert [index for _, index, _ in loop.calls] == indices[1:]   # each its own frame
    due = [i for i in range(5, 201) if i % 3 == 0]
    assert loop.cap.late > 0 and len(past) + loop.cap.late == len(due)
    assert loop.lost == 0   # a dropped frame is a gap, not a lost one
    assert loop.cap.cap.released


class _Watching(_FakeModel):
    """A Bullet Hole at (15, 15) on the frames `on(index)` says. Prints each
    frame it looks at, and sends `signum` from the first look at or past
    `stop_at`, as an operator stopping the run would."""
    def __init__(self, on, stop_at, signum=signal.SIGINT):
        self.on, self.stop_at, self.signum = on, stop_at, signum

    def predict(self, image, imgsz, conf, verbose=False, classes=None):
        index = int(image[0, 0, 0])
        print(f"[LOOK] {index}")
        if index >= self.stop_at:
            os.kill(os.getpid(), self.signum)
        return super().predict(image, imgsz, conf) if self.on(index) \
            else [types.SimpleNamespace(boxes=[])]


def _live_run(monkeypatch, model, changed=lambda index: True, stride=5):
    """`process` on an endless stream, a frame every 2 ms; change detection
    sees the mark on the frames `changed(index)` says."""
    loop = _live(monkeypatch, _FakeStream(interval=0.002))
    loop.model = model
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    monkeypatch.setattr(nbh.board, "changed_regions",
                        lambda a, b: np.full((64, 64), changed(int(b[0, 0, 0])), bool))
    return nbh.process("rtsp://mtx:8554/cam", None, None, "model.pt", stride=stride)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_a_stop_signal_ends_a_live_run_and_the_full_report_still_prints(
        monkeypatch, capsys, signum):
    before = signal.getsignal(signum)
    run = _live_run(monkeypatch, _Watching(lambda i: i >= 6, stop_at=80, signum=signum))
    out = capsys.readouterr().out
    assert len(run.holes) == 1
    assert "[INFO] 1 new Bullet Holes" in out and "[GROUP]" in out
    assert signal.getsignal(signum) is before


def _lines_after_looks(out):
    """The output's lines, and the frames looked at, in order."""
    lines = out.splitlines()
    return lines, [int(l.split()[1]) for l in lines if l.startswith("[LOOK]")]


def test_a_live_bullet_hole_is_printed_once_as_soon_as_its_window_elapses(
        monkeypatch, capsys):
    """Printed at the first look past its persistence window, with the wall
    clock it was first seen at, and never again (#83)."""
    run = _live_run(monkeypatch, _Watching(lambda i: i >= 6, stop_at=120))
    lines, looked = _lines_after_looks(capsys.readouterr().out)
    first = next(i for i in looked if i >= 6)
    elapsed = next(i for i in looked if i + 1 >= first + nbh.PERSIST_FRAMES)
    new = [n for n, line in enumerate(lines) if line.startswith("[NEW]")]
    assert len(new) == 1
    assert lines[new[0] - 1] == f"[LOOK] {elapsed}"
    assert re.search(r"t=\d\d:\d\d:\d\d\.\d\d  MISS", lines[new[0]])
    assert [h["first_frame"] for h in run.holes] == [first]   # the report's is the one announced


def test_the_end_of_a_live_run_reports_what_was_announced_and_nothing_else(
        monkeypatch, capsys):
    """The report lists exactly the Bullet Holes announced: one it dropped
    would be retracted (ADR-0004). Change evidence here stops before the
    mark's window ends, the setting in which a drifting position could lose it."""
    run = _live_run(monkeypatch, _Watching(lambda i: i >= 6, stop_at=120),
                    changed=lambda index: index <= 20)
    out = capsys.readouterr().out
    assert out.count("[NEW]") == 1 and len(run.holes) == 1
    assert "[FILTER] change evidence required: 1 -> 1" in out


def test_a_confirmed_live_bullet_hole_waits_for_change_evidence(monkeypatch, capsys):
    """Confirmed at its window's end but not corroborated until frame 90:
    printed then, once (#83)."""
    _live_run(monkeypatch, _Watching(lambda i: i >= 6, stop_at=120),
              changed=lambda index: index >= 90)
    lines, looked = _lines_after_looks(capsys.readouterr().out)
    new = [n for n, line in enumerate(lines) if line.startswith("[NEW]")]
    assert len(new) == 1
    assert lines[new[0] - 1] == f"[LOOK] {next(i for i in looked if i >= 90)}"


def test_a_live_run_reports_the_configured_fps_beside_the_measured_arrival_rate(
        monkeypatch, capsys):
    """At the live default stride. A frame every 2 ms or more arrives at no
    more than 500 fps, against the 25 configured (#83)."""
    _live_run(monkeypatch, _Watching(lambda i: False, stop_at=60), stride=None)
    out = capsys.readouterr().out
    rate = re.search(r"\[LIVE\] configured 25 fps; frames arrived at ([\d.]+) fps", out)
    assert rate and 0 < float(rate[1]) <= 500
    assert f"[INFO] stride {nbh.LIVE_STRIDE}:" in out
    _, looked = _lines_after_looks(out)
    assert all(i % nbh.LIVE_STRIDE == 0 for i in looked[nbh.BASELINE_FRAMES:])


def test_a_stream_bypasses_the_manifest_gate(monkeypatch):
    """rtsps too: gated as a file, its URL reached a traceback, password and all."""
    monkeypatch.setattr(nbh.manifest, "authorise",
                        lambda *args, **kwargs: pytest.fail("a stream was gated"))
    for url in ("rtsp://mtx:8554/cam", "rtsps://operator:secret@mtx:8322/cam"):
        assert nbh._gate(url, False, "model.pt") is None


def test_an_unregistered_file_is_still_refused(tmp_path):
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"in no manifest")
    with pytest.raises(SystemExit, match=r"\[REFUSED\]"):
        nbh._gate(str(clip), False, "model.pt")


def test_credentials_in_a_stream_url_are_never_printed(monkeypatch, capfd):
    """Through real OpenCV, on a port nothing listens on: OpenCV's default
    backends print a URL they cannot open, password and all (#83)."""
    monkeypatch.setitem(sys.modules, "ultralytics",
                        types.SimpleNamespace(YOLO=lambda path: _FakeModel()))
    monkeypatch.setattr(nbh.cv2, "imread", lambda path: np.zeros((8, 8, 3), np.uint8))
    monkeypatch.setattr(nbh.board, "find_targets", lambda image, min_area=None: ([None], None))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(SystemExit) as refused:
        nbh.RegisteredFrames.open(f"rtsp://operator:secret@127.0.0.1:{port}/cam",
                                  None, "model.pt")
    out, err = capfd.readouterr()
    shown = out + err + str(refused.value)
    url = f"rtsp://127.0.0.1:{port}/cam"
    assert url in out and url in str(refused.value)
    assert "secret" not in shown and "operator" not in shown


# --- recovering from a stream drop (#84) ---------------------------------------


def test_a_stream_that_drops_is_reopened_and_iteration_continues(monkeypatch, capsys):
    """Down after 20 frames, and the first reopen fails too. Indices count on
    across the drop, the frames it missed are gaps, and registration resumes
    from the last view before it, in the same Board space (#84)."""
    reopened = iter([_FakeStream(n=0), _FakeStream(interval=0.002)])
    loop = _live(monkeypatch, _FakeStream(n=20, interval=0.002), lambda: next(reopened))
    monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.1)
    view = loop.view
    # A baseline as long as the run: each frame waits its turn, none is late.
    indices = [l.index for l in loop.looks(60, stride=1, baseline_frames=60)]
    (seconds, missed), = loop.cap.drops
    assert seconds >= 0.2 and missed >= 1
    assert indices == list(range(21)) + list(range(21 + missed, 60))
    assert loop.lost == 0 and loop.view is view
    how, index, last = loop.calls[20]   # the first look after the drop
    assert how == "track" and index == 1 and last.index == 20
    out = capsys.readouterr().out
    assert out.count("[LIVE] stream dropped") == 1
    assert re.search(rf"\[LIVE\] stream back .* after {seconds:.1f} s without a frame: "
                     rf"{missed} frame\(s\) missed", out)
    assert re.search(rf"\[LIVE\] 1 drop\(s\), {seconds:.1f} s down in all, {missed} "
                     rf"frame\(s\) missed", out)


class _Stalling(_FakeStream):
    """`n` frames, then a read that hangs `seconds` and still returns a frame,
    as FFmpeg's does when its timeout cuts a stalled read short (measured over
    HTTP on a spent recording, #84); later reads fail."""
    def __init__(self, n, seconds):
        super().__init__(n=n + 1, interval=0.002)
        self.seconds = seconds

    def grab(self):
        if self.at == self.n - 1:
            time.sleep(self.seconds)
        return super().grab()


def test_a_read_cut_short_by_the_timeout_is_a_drop_from_the_frame_before_it(
        monkeypatch):
    monkeypatch.setattr(nbh, "STREAM_TIMEOUT_MS", 100)
    loop = _live(monkeypatch, _Stalling(n=10, seconds=0.15),
                 lambda: _FakeStream(interval=0.002))
    indices = [l.index for l in loop.looks(30, stride=1, baseline_frames=30)]
    (seconds, missed), = loop.cap.drops
    assert seconds >= 0.15
    assert indices == list(range(11)) + list(range(11 + missed, 30))
    assert loop.calls[10][1] == 1   # the reopened stream's first, not the stalled one


def test_a_drop_during_the_baseline_leaves_it_consecutive_frames(monkeypatch):
    """Indices jump past the drop, but the baseline is still its first frames
    in a row, not frames a stride apart from the end of the drop (#84)."""
    loop = _live(monkeypatch, _FakeStream(n=2, interval=0.002),
                 lambda: _FakeStream(interval=0.002))
    monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.1)
    indices = [l.index for l in loop.looks(60, stride=3, baseline_frames=5)]
    (_, missed), = loop.cap.drops
    back = 3 + missed
    assert missed >= 1 and indices[:5] == [0, 1, 2, back, back + 1]
    assert all(i % 3 == 0 for i in indices[5:])


def test_a_drop_still_open_when_the_run_stops_is_in_the_totals(monkeypatch, capsys):
    """Down for good after 20 frames: its first reopen stops the run (#84)."""
    loop = _live(monkeypatch, _FakeStream(n=20, interval=0.001))
    list(loop.looks(math.inf, stride=1, baseline_frames=5))
    out = capsys.readouterr().out
    assert re.search(r"\[LIVE\] 1 drop\(s\), [\d.]+ s down in all, 0 frame\(s\) missed; "
                     r"the last still down at the end", out)


def test_a_stream_is_opened_with_a_bounded_read_timeout(monkeypatch):
    """So a connection that stays open but stops delivering frames fails a
    read within it, a drop to recover from, instead of blocking for FFmpeg's
    30 s (#84). Opening is bounded too, so reopening keeps its pace."""
    opened = []
    monkeypatch.setattr(nbh.cv2, "VideoCapture", lambda *args: opened.append(args))
    nbh._open_stream("rtsp://mtx:8554/cam")
    (url, api, params), = opened
    assert url == "rtsp://mtx:8554/cam" and api == nbh.cv2.CAP_FFMPEG
    timeouts = dict(zip(params[::2], params[1::2]))
    assert timeouts == {nbh.cv2.CAP_PROP_OPEN_TIMEOUT_MSEC: nbh.STREAM_TIMEOUT_MS,
                        nbh.cv2.CAP_PROP_READ_TIMEOUT_MSEC: nbh.STREAM_TIMEOUT_MS}
