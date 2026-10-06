"""Checks for the shared registered-frame loop. No model, no video, no torch.

The loop exists so the pipeline and the detector probe look at the same image.
What is testable without a video file is the bookkeeping the probe depends on:
which frames got a look, and which only appeared to.
"""
import itertools
import sys
import types

import numpy as np

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
          disagreement=lambda i: 0.0):
    """A loop over `frames` frames; `registers(index)` says which ones register
    when tracked, `reanchors(index)` which when re-anchored (#80), and
    `below(index)` how far that frame's view runs past the canvas bottom,
    in Board px against a 100 px Target span — None for an unmeasurable view.
    A fit converges at `correlation(index)`, and an independent silhouette fit
    disagrees with it by `disagreement(index)` Board px (#110).

    `loop.calls` records `(how, index, last)` for each frame read, where `how`
    is "track" or "reanchor" and `last` is the view it was handed;
    `loop.silhouetted` the indices whose fit was checked against the silhouette."""
    seen = iter(range(1, frames + 1))
    calls, checked = [], []
    def fit(how, succeeds):
        def call(frame, *args):
            index, last = next(seen), args[-1]
            calls.append((how, index, last))
            if not succeeds(index):
                return None, None
            view = _FakeView()
            view.index = index
            return view, correlation(index)
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
    loop = nbh.RegisteredFrames(_FakeCap(frames), _FakeModel(), _FakeView(),
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


def test_render_draws_each_frame_with_the_view_detection_used(monkeypatch):
    """`_render` registers nothing (#80): a re-anchored view is drawn from its
    frame on, and a lost frame keeps the last view before it."""
    drawn = []

    class _Named(_FakeView):
        targets = []

        def __init__(self, name):
            self.name = name

        def rectify(self, frame):
            drawn.append(self.name)
            return np.zeros((64, 64, 3), np.uint8)

    class _Writer:
        def write(self, image):
            pass

        def release(self):
            pass

    monkeypatch.setattr(nbh.cv2, "VideoCapture", lambda video: _FakeCap(5))
    monkeypatch.setattr(nbh.cv2, "VideoWriter", lambda *args: _Writer())
    monkeypatch.setattr(nbh.board, "track_view",
                        lambda *args: (_ for _ in ()).throw(AssertionError("re-registered")))
    views = {0: _Named("base"), 1: _Named("base"), 3: _Named("re-anchored")}
    nbh._render("clip.mp4", 0.0, 5, 25.0, views, [], [], "out.mp4")
    assert drawn == ["base", "base", "base", "re-anchored", "re-anchored"]


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
    assert _reanchored(loop) == [N + 1]
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
