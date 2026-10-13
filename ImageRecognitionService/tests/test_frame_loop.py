"""Checks for the shared registered-frame loop. No model, no video, no torch.

The loop exists so the pipeline and the detector probe look at the same image.
What is testable without a video file is the bookkeeping the probe depends on:
which frames got a look, and which only appeared to.
"""
import math
import os
import re
import signal
import socket
import sys
import time
import types
from datetime import datetime, timedelta, timezone

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
    tpl_to_board = np.eye(3)
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


class _Scripted:
    """A `Registration` whose verdicts are scripted: a frame registers when
    `registers(index)` says so, as a `_FakeView` marked with the frame's
    pixels. `calls` records `(index, pixels)` for each frame handed to it,
    and `reported` how often the end-of-run report was asked for."""
    def __init__(self, view, registers):
        self.last, self.registers, self.calls, self.reported = view, registers, [], 0

    def register(self, frame, index):
        pixels = int(frame[0, 0, 0])
        self.calls.append((index, pixels))
        if not self.registers(index):
            return None
        self.last = _FakeView()
        self.last.index = pixels
        return self.last

    def report(self):
        self.reported += 1


def _loop(registers=lambda i: True, frames=10, source=None, view=None, registration=None):
    """A loop over `frames` frames onto Board space `view`, registering those
    `registers(index)` says, unless a `registration` is given."""
    view = view or _FakeView()
    return nbh.RegisteredFrames(source or nbh.Recording(_FakeCap(frames), fps=25.0, start=10.0),
                                _FakeModel(), view, np.zeros((8, 8, 3), np.uint8), imgsz=64,
                                conf=0.02,
                                registration=registration or _Scripted(view, registers))


def test_a_lost_frame_is_not_a_frame_that_saw_nothing():
    """The whole point of the Look: the probe must not score a lost frame as a miss."""
    loop = _loop(lambda i: i != 3)
    looks = list(loop.looks(5))

    lost = [l for l in looks if not l.registered]
    assert len(lost) == 1 and lost[0].index == 3
    assert lost[0].detections is None          # not an empty array
    assert all(len(l.detections) == 1 for l in looks if l.registered)
    assert (loop.processed, loop.lost) == (5, 1)


def test_indices_keep_counting_across_a_lost_frame():
    """Frame numbers are positions in the clip, not positions in the output."""
    loop = _loop(lambda i: i not in (2, 3))
    assert [l.index for l in loop.looks(6)] == [0, 1, 2, 3, 4, 5]


def test_the_first_frame_is_the_one_board_space_was_built_from():
    """It is already read and already registered, and still yielded like any other."""
    loop = _loop()
    first = next(loop.looks(4))
    assert first.index == 0 and first.view is loop.view
    assert loop.registration.calls == []   # never handed to registration


def test_a_short_file_stops_early_rather_than_padding():
    """`processed` is what confirmation is measured against, so it must be real."""
    loop = _loop(frames=2)
    assert len(list(loop.looks(50))) == 3      # the baseline frame plus two reads
    assert loop.processed == 3


def test_the_capture_is_released_when_iteration_ends():
    loop = _loop(frames=2)
    list(loop.looks(50))
    assert loop.source.cap.released and loop.registration.reported == 1


def test_frames_until_counts_from_the_start_timestamp():
    loop = _loop()
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


def test_a_canvas_that_did_not_grow_is_shown_to_the_detector_once():
    """No Board past the margin canvas: one inference on the canvas, as before #46."""
    model = _RecordingModel()
    loop = _loop(frames=1)
    loop.model = model
    looks = list(loop.looks(2))
    assert len(model.calls) == 2 and all(imgsz == 64 for _, _, imgsz in model.calls)
    assert looks[0].inner is looks[0].canvas


def test_a_grown_canvas_is_searched_as_the_margin_canvas_plus_its_bands():
    """A on the margin canvas at the loop's imgsz; B on each band at its own;
    B keeps only what lies past the margin canvas, in grown-canvas px."""
    model = _RecordingModel()
    loop = _loop(frames=0, view=_GrownView())
    loop.model = model
    look = next(loop.looks(1))
    assert model.calls == [((64, 64), 1, 64), ((48, 64), 7, 64)]
    assert look.detections[:, :2].tolist() == [[15.0, 15.0], [30.0, 72.0]]
    assert look.inner.shape == (64, 64, 3) and look.canvas.shape == (80, 64, 3)


def _openable(monkeypatch):
    """`RegisteredFrames.open` on a one-frame `_FakeCap`, every Target found
    and Board space built without a model, artwork or geometry."""
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


def test_opening_reports_how_long_building_board_space_took(monkeypatch, capsys):
    """Wall time from opening the source to Board space built, printed once (#79).
    The value is the machine's, so only that it is reported is checked."""
    _openable(monkeypatch)
    nbh.RegisteredFrames.open("clip.mkv", 10.0, "model.pt")
    assert capsys.readouterr().out.count("[REGISTRATION] Board space built in ") == 1


def test_a_recording_times_its_frames_from_ref_time_or_when_it_was_opened(monkeypatch):
    """`--ref-time` is the wall clock at the Recording's t=0, and without it
    the time the run opened the Recording (#152)."""
    _openable(monkeypatch)
    ref = datetime(2026, 10, 11, 10, 30, tzinfo=timezone.utc)
    loop = nbh.RegisteredFrames.open("clip.mkv", 10.0, "model.pt", ref_time=ref)
    assert loop.wall_clock(13) == ref + timedelta(seconds=10.52)
    before = datetime.now(timezone.utc)
    loop = nbh.RegisteredFrames.open("clip.mkv", 10.0, "model.pt")
    t0 = loop.wall_clock(0) - timedelta(seconds=10)
    assert before <= t0 <= datetime.now(timezone.utc)


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
    loop = _loop()
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    rendered = []
    monkeypatch.setattr(nbh, "_render", lambda video, start, n, fps, views, *rest:
                        rendered.append((n, views)))
    nbh.process("clip.mp4", 10.0, 10.0, "model.pt", out_video="out.mp4")
    assert rendered == [(0, {0: loop.view})]


def test_rendering_gets_the_view_of_every_frame_read(monkeypatch):
    """Views are kept only for `--out` (#80); when they are, none is missing."""
    loop = _loop()
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    rendered = []
    monkeypatch.setattr(nbh, "_render", lambda video, start, n, fps, views, *rest:
                        rendered.append(sorted(views)))
    nbh.process("clip.mp4", 10.0, 10.4, "model.pt", out_video="out.mp4")
    assert rendered == [list(range(10))]


def test_the_pipeline_hands_persistence_the_frames_it_lost(monkeypatch, capsys):
    """The #110 floor counts frames tried and lost, so `process` must hand
    `Persistence` each Lost Look; the Board-lost warning counts what it holds.
    The one loop test with the real `Registration` in it (#138): frames 7 and
    8 do not register."""
    monkeypatch.setattr(nbh.board, "track_view", lambda frame, last: (
        (None, None) if frame[0, 0, 0] in (7, 8) else (_FakeView(), 0.95)))
    monkeypatch.setattr(nbh.board, "uncovered_view", lambda view, size: (
        0.0, dict.fromkeys(("left", "right", "above", "below"), 0.0)))
    view = _FakeView()
    # `when` is never called: nothing here re-anchors.
    loop = _loop(view=view, registration=nbh.Registration(view, (8, 8), None, str))
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    nbh.process("clip.mp4", 10.0, 10.4, "model.pt")
    assert "[WARN] Board lost on 2 frame(s);" in capsys.readouterr().out


# --- a stride: look at every Nth frame (#81) ---------------------------------


def test_a_stride_looks_at_the_first_frames_then_its_multiples_past_them():
    """The baseline's frames 0..B-1 are all looked at whatever the stride; past
    them, only multiples of the stride at or after B (#81)."""
    for stride, expected in [(13, [0, 1, 2, 3, 4, 13, 26, 39, 52]),
                             (2, [0, 1, 2, 3, 4, 6, 8, 10]),
                             (1, list(range(11)))]:
        loop = _loop(frames=60)
        last = expected[-1] + 1
        assert [l.index for l in loop.looks(last, stride, 5)] == expected


def test_frames_a_stride_skips_are_neither_registered_nor_yielded():
    """A skipped frame is a gap, not a lost frame: never decoded, never fitted."""
    loop = _loop(frames=30)
    looks = list(loop.looks(30, 13, 5))
    assert [pixels for _, pixels in loop.registration.calls] == [1, 2, 3, 4, 13, 26]
    assert all(l.registered for l in looks)
    assert loop.source.cap.grabbed == [i for i in range(5, 30) if i % 13]
    assert (loop.processed, loop.lost) == (30, 0)


def test_a_stride_stops_at_the_end_of_the_file():
    """A failed grab is the end of the file too, so `processed` stays real."""
    loop = _loop(frames=20)
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
    loop = _loop(frames=100)
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
    `_FakeCap`. Read through `grab` and `retrieve`, as the reader thread does,
    and each frame's timestamp through `get`: `ms(index)`, by default one
    frame interval at `LIVE_FPS` a frame (#117)."""
    def __init__(self, n=None, interval=0.0, ms=None):
        self.n, self.interval, self.at, self.released = n, interval, 0, False
        self.ms = ms or (lambda at: at * 1000 / nbh.LIVE_FPS)

    def grab(self):
        if self.n is not None and self.at >= self.n:
            return False
        time.sleep(self.interval)
        self.at += 1
        return True

    def retrieve(self):
        return True, np.full((8, 8, 3), self.at, np.int64)

    def get(self, prop):
        assert prop == nbh.cv2.CAP_PROP_POS_MSEC
        return self.ms(self.at)

    def release(self):
        self.released = True


class _Losing(_FakeStream):
    """`_FakeStream`, losing `lost` frames upstream after frame `after`: they
    never arrive, and the next frame's index and timestamp are past them, as
    MediaMTX discarding for a slow reader leaves them (#85)."""
    def __init__(self, after, lost, **kwargs):
        super().__init__(**kwargs)
        self.after, self.lost = after, lost

    def grab(self):
        if self.at == self.after:
            self.at += self.lost
        return super().grab()


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
    live = nbh.Stream(stream, time.time(), reopen or stop)
    return _loop(source=live)


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
    assert [pixels for _, pixels in loop.registration.calls] == indices[1:]   # each its own frame
    due = [i for i in range(5, 201) if i % 3 == 0]
    assert loop.source.late > 0 and len(past) + loop.source.late == len(due)
    assert loop.lost == 0   # a dropped frame is a gap, not a lost one
    assert loop.source.cap.released


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


def test_a_live_run_reports_its_rate_and_the_frames_it_looked_at(monkeypatch, capsys):
    """At the live default stride. Frames read every 2 ms, a backlog's pace,
    but 40 ms apart by the stream's timestamps: the rate is theirs, 25 fps,
    not the reads' (#117); #85's report to #78 asks for the frames looked at,
    baseline included."""
    _live_run(monkeypatch, _Watching(lambda i: False, stop_at=60), stride=None)
    out = capsys.readouterr().out
    assert re.search(r"\[LIVE\] configured 25 fps; by the stream's timestamps, frames "
                     r"step at 25\.00 fps, and were received at 25\.00 fps over [\d.]+ s "
                     r"of stream\.", out)
    assert f"[INFO] stride {nbh.LIVE_STRIDE}:" in out
    _, looked = _lines_after_looks(out)
    assert all(i % nbh.LIVE_STRIDE == 0 for i in looked[nbh.BASELINE_FRAMES:])
    assert f"[LIVE] {len(looked)} frame(s) looked at;" in out


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
    across the drop, the frames it missed are gaps, and the reopened stream's
    first frame goes to the same registration, in the same Board space (#84)."""
    reopened = iter([_FakeStream(n=0), _FakeStream(interval=0.002)])
    loop = _live(monkeypatch, _FakeStream(n=20, interval=0.002), lambda: next(reopened))
    monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.1)
    view = loop.view
    # A baseline as long as the run: each frame waits its turn, none is late.
    indices = [l.index for l in loop.looks(60, stride=1, baseline_frames=60)]
    (seconds, missed), = loop.source.drops
    assert seconds >= 0.2 and missed >= 1
    assert indices == list(range(21)) + list(range(21 + missed, 60))
    assert loop.source.unseen == list(range(21, 21 + missed))   # stride 1: all were due
    assert loop.lost == 0 and loop.view is view
    assert loop.registration.calls[20] == (21 + missed, 1)   # the first look after the drop
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
    (seconds, missed), = loop.source.drops
    assert seconds >= 0.15
    assert indices == list(range(11)) + list(range(11 + missed, 30))
    assert loop.registration.calls[10][1] == 1   # the reopened stream's first, not the stalled one


class _Undecodable(_FakeStream):
    """Grabs, but its first `failures` frames do not decode."""
    def __init__(self, failures):
        super().__init__(interval=0.002)
        self.failures = failures

    def retrieve(self):
        if self.failures:
            self.failures -= 1
            return False, None
        return super().retrieve()


def test_a_reopened_stream_that_cannot_decode_is_still_the_same_drop(monkeypatch, capsys):
    """Grabbed but not decoded is no frame received: the drop stays open
    through it, one drop as long as the whole outage, not two (#84)."""
    reopened = iter([_Undecodable(failures=1), _FakeStream(interval=0.002)])
    loop = _live(monkeypatch, _FakeStream(n=20, interval=0.002), lambda: next(reopened))
    monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.1)
    indices = [l.index for l in loop.looks(60, stride=1, baseline_frames=60)]
    (seconds, missed), = loop.source.drops
    assert seconds >= 0.2
    assert indices == list(range(21)) + list(range(21 + missed, 60))
    assert capsys.readouterr().out.count("[LIVE] stream dropped") == 1


def test_a_window_a_drop_emptied_confirms_nothing(monkeypatch, capsys):
    """Seen on every look from frame 20, past the baseline, to a drop at 30
    longer than its window: the looks after are past it, so it was seen in
    100% of the few it got. The due
    frames the drop missed count against the floor, so it is unconfirmable,
    not a Bullet Hole announced on reconnect (#84)."""
    monkeypatch.setattr(nbh, "LIVE_FPS", 1000)   # a 0.1 s drop misses ~100 frames
    after = _FakeStream(interval=0.002)
    after.at = 1000   # its pixels, which `_Watching` reads, apart from the first stream's
    loop = _live(monkeypatch, _FakeStream(n=30, interval=0.002), lambda: after)
    monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.1)
    loop.model = _Watching(lambda i: 20 <= i < 1000, stop_at=1200)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    monkeypatch.setattr(nbh.board, "changed_regions",
                        lambda a, b: np.ones((64, 64), bool))
    run = nbh.process("rtsp://mtx:8554/cam", None, None, "model.pt", stride=1)
    (_, missed), = loop.source.drops
    assert missed >= nbh.PERSIST_FRAMES
    assert "[NEW]" not in capsys.readouterr().out and run.holes == []


def test_a_drop_during_the_baseline_leaves_it_consecutive_frames(monkeypatch):
    """Indices jump past the drop, but the baseline is still its first frames
    in a row, not frames a stride apart from the end of the drop (#84)."""
    loop = _live(monkeypatch, _FakeStream(n=2, interval=0.002),
                 lambda: _FakeStream(interval=0.002))
    monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.1)
    indices = [l.index for l in loop.looks(60, stride=3, baseline_frames=5)]
    (_, missed), = loop.source.drops
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


# --- indexing by the stream's timestamps (#117) --------------------------------


def test_frames_lost_upstream_leave_a_gap_in_the_indices(monkeypatch):
    """100 frames lost after frame 10 make an index gap of 100, not a shift:
    every look after it is the frame its index names (#117)."""
    loop = _live(monkeypatch, _Losing(after=10, lost=100, interval=0.002))
    indices = [l.index for l in loop.looks(150, stride=1, baseline_frames=150)]
    assert indices == list(range(11)) + list(range(111, 150))
    assert [pixels for _, pixels in loop.registration.calls] == indices[1:]   # the frame read


def test_a_window_emptied_upstream_confirms_nothing(monkeypatch, capsys):
    """Seen on every look from frame 20, past the baseline, to a gap of 100
    frames lost upstream after frame 30: seen on every look after it too,
    which once filled its window with the shifted indices. The due frames
    lost count against the floor, so it is unconfirmable (#117)."""
    loop = _live(monkeypatch, _Losing(after=30, lost=100, interval=0.002))
    loop.model = _Watching(lambda i: i >= 20, stop_at=200)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    monkeypatch.setattr(nbh.board, "changed_regions",
                        lambda a, b: np.ones((64, 64), bool))
    run = nbh.process("rtsp://mtx:8554/cam", None, None, "model.pt", stride=1)
    assert loop.source.unseen == list(range(31, 131))   # stride 1: all were due
    assert "[NEW]" not in capsys.readouterr().out and run.holes == []


def test_a_gap_upstream_is_logged_when_found_and_in_the_totals(monkeypatch, capsys):
    """100 frames lost after frame 10, at stride 3: 33 of them due a look,
    12 to 108. Logged when found, with the stream time it covers, and in the
    end-of-run totals (#117)."""
    loop = _live(monkeypatch, _Losing(after=10, lost=100, n=150, interval=0.002))
    list(loop.looks(math.inf, stride=3, baseline_frames=5))
    out = capsys.readouterr().out
    assert re.search(r"\[LIVE\] 100 frame\(s\) lost upstream, 4\.0 s of stream before "
                     r"\d\d:\d\d:\d\d\.\d\d: 33 of them due a look, counted against "
                     r"persistence's floor\. Frames up to the next keyframe may decode "
                     r"corrupt \(#117\)", out)
    assert re.search(r"\[LIVE\] 1 gap\(s\) upstream, 100 frame\(s\) lost, 33 of them due "
                     r"a look; 0 frame\(s\) untimed", out)
    # 50 frames after frame 0 came, over the 6 s (150 frames) of stream they span.
    assert "frames step at 25.00 fps, and were received at 8.33 fps over 6.0 s" in out


# Frame 10 an extra one, stamped with frame 9's timestamp, as are the rest one
# frame behind.
_REPEATED = lambda at: (at - (at >= 10)) * 40
_STEPS = r"by the stream's timestamps, frames step at 25\.00 fps"
_WALL_CLOCK = r"frames arrived at [\d.]+ fps by the wall clock, over 31 frame\(s\)"


@pytest.mark.parametrize("ms, untimed, rate, timed", [
    (_REPEATED, 1, _STEPS, None),
    # Frame 10 stamped with frame 9's timestamp, and the rest on time: no
    # frame after it is lost (Codex on #121).
    (lambda at: (at - (at == 10)) * 40, 1, _STEPS, None),
    # Zero until frame 5, then absolute: not 5000 s lost (Codex on #121).
    (lambda at: 0.0 if at < 5 else 5e6 + at * 40, 4, _STEPS, None),
    # Reset to 0 at frame 10: behind the last frame a step timed, so one past
    # the frame before, not a gap (Codex on #121).
    (lambda at: (at - 10 * (at >= 10)) * 40, 1, _STEPS, None),
    # A backend with no timestamps at all: the wall-clock arrival rate, as
    # before #117.
    (lambda at: 0.0, 30, _WALL_CLOCK, 0),
    # Advancing for 5 frames, then frozen for 25: not the 5's rate, measured
    # (Codex on #121).
    (lambda at: min(at, 5) * 40, 25, _WALL_CLOCK, 5),
    # Advancing for 12 frames, then 9 repeated and the 9 after them resuming:
    # only the 12 steps are timed, not 12 against 9 untimed (Codex on #121).
    (lambda at: (at - (at > 12 and at % 2)) * 40, 9, _WALL_CLOCK, 12),
])
def test_a_timestamp_not_later_than_the_one_before_is_placed_one_past_it(
        monkeypatch, capsys, ms, untimed, rate, timed):
    """And counted: with no usable timestamps for most frames, frames are
    counted as they were before #117, and the report warns so and measures
    the rate frames arrived at instead (#83)."""
    loop = _live(monkeypatch, _FakeStream(n=30, interval=0.002, ms=ms))
    assert [l.index for l in loop.looks(31, stride=1, baseline_frames=31)] == list(range(31))
    out = capsys.readouterr().out
    assert re.search(rf"\[LIVE\] 0 gap\(s\) upstream, 0 frame\(s\) lost, 0 of them due a "
                     rf"look; {untimed} frame\(s\) untimed", out)
    assert re.search(rf"\[LIVE\] configured 25 fps; {rate}", out)
    warned = _coverage_warning(out)
    assert (warned and warned[0]) == timed
    if warned:   # no drops, so the rest is frame 0, the untimed and the resumed
        _, received, untimed_, _, reconnected = warned
        assert (received, untimed_, reconnected) == (31, untimed, 0)


def _coverage_warning(out):
    """The low timestamp coverage warning's counts: frames timed, received,
    untimed, the first to advance after an untimed one, and the first after
    a drop; checked to account for every frame received, frame 0 included."""
    warned = re.search(r"\[WARN\] the stream's timestamps timed only (\d+) of (\d+) frame\(s\)\. "
                       r"The rest were not timed by a step: frame 0, (\d+) untimed, "
                       r"(\d+) the first to advance after one, and (\d+) the first after a "
                       r"drop\.", out)
    if not warned:
        return None
    timed, received, untimed, resumed, reconnected = map(int, warned.groups())
    assert 1 + timed + untimed + resumed + reconnected == received
    return timed, received, untimed, resumed, reconnected


class _UndecodableAfterOne(_FakeStream):
    """`_FakeStream`, whose second frame advances but does not decode."""
    def retrieve(self):
        return (False, None) if self.at == 2 else super().retrieve()


@pytest.mark.parametrize("session", [
    lambda: _FakeStream(n=1, interval=0.002),
    # Its second frame's step is no frame received, so not timed either
    # (Codex on #121).
    lambda: _UndecodableAfterOne(interval=0.002),
])
def test_a_stream_that_keeps_reconnecting_still_warns_its_timestamps_timed_none(
        monkeypatch, capsys, session):
    """One frame received a session: each is the first of its RTSP session,
    so none is timed by a step, and none is untimed either. Still warned,
    with why (Codex on #121)."""
    loop = _live(monkeypatch, _FakeStream(n=0), session)
    list(loop.looks(10, stride=1, baseline_frames=10))
    timed, received, untimed, resumed, reconnected = _coverage_warning(
        capsys.readouterr().out)
    assert (timed, untimed, resumed) == (0, 0, 0) and received >= 3
    assert reconnected == len(loop.source.drops)


@pytest.mark.parametrize("ms, after, lost", [
    (_REPEATED, 20, 1),
    # Frame 10 stamped with frame 9's timestamp, and the 100 after it lost:
    # placed from frame 9, the last a step timed, not one past frame 10
    # (Codex on #121).
    (lambda at: (at - (at == 10)) * 40, 10, 100),
])
def test_a_loss_after_a_repeated_timestamp_is_still_a_gap(
        monkeypatch, capsys, ms, after, lost):
    """Indexing restarts from the frame after the untimed one, so the frame
    lost after it, at 20, is a gap of one, not absorbed by the one-frame
    shift; and frames lost before it, measured from the last frame a step
    timed, are a gap too (#117). Either way the rate is every frame received
    over all the stream time to the last: the loss shows in it (Codex on #121)."""
    loop = _live(monkeypatch, _Losing(after=after, lost=lost, interval=0.002, ms=ms))
    end = after + lost + 20
    indices = [l.index for l in loop.looks(end, stride=1, baseline_frames=end)]
    assert indices == list(range(after + 1)) + list(range(after + lost + 1, end))
    assert loop.source.upstream == [(lost, lost)] and loop.source.untimed == 1
    span = ms(loop.source.received - 1 + lost) / 1000   # to the last frame received
    _assert_received_rate(capsys.readouterr().out, loop.source.received - 1, span)


def _assert_received_rate(out, frames, span):
    """The report's rate by the stream's timestamps is `frames` received over
    `span` s of stream, to its rounding."""
    rate = re.search(r"were received at ([\d.]+) fps over ([\d.]+) s of stream", out)
    assert float(rate[2]) == pytest.approx(span, abs=0.051)
    assert float(rate[1]) == pytest.approx(frames / span, abs=0.01)


class _CorruptAfterTheGap(_Losing):
    """`_Losing`, and the first frame after the gap comes 0.5 s late, as to a
    reader that stalled, and does not decode."""
    def grab(self):
        if self.at == self.after:
            time.sleep(0.5)
        return super().grab()

    def retrieve(self):
        if self.at == self.after + self.lost + 1:
            return False, None
        return super().retrieve()


def test_a_gap_upstream_is_kept_when_the_frame_after_it_does_not_decode(
        monkeypatch, capsys):
    """100 frames lost after frame 10, and frame 111 grabbed but not decoded:
    a drop from it, but the 100 are still a gap upstream, and indices after
    the drop are past them. The drop runs from frame 111, a frame after the
    last lost one: the stall before it is the gap's, not counted twice. And
    the rate spans the gap too, frame 111 not received (Codex on #121)."""
    loop = _live(monkeypatch, _CorruptAfterTheGap(after=10, lost=100, interval=0.002),
                 lambda: _FakeStream(interval=0.002))
    monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.1)
    indices = [l.index for l in loop.looks(200, stride=1, baseline_frames=200)]
    (seconds, missed), = loop.source.drops
    assert 0.1 + 1 / nbh.LIVE_FPS <= seconds < 0.5
    back = 111 + missed   # the drop missed frame 111 onwards
    assert indices == list(range(11)) + list(range(back, 200))
    assert loop.source.upstream == [(100, 100)] and loop.source.unseen == list(range(11, back))
    # Frames 1-10 and 111 span 4.44 s; the new session's frames after its first
    # (frame 0 and it are origins) 40 ms each.
    received = loop.source.received
    _assert_received_rate(capsys.readouterr().out, received - 2, (received + 99) * 0.04)


def test_the_baseline_is_its_first_frames_read_across_a_gap_upstream(monkeypatch):
    """100 frames lost after frame 10, inside a 20-frame baseline: the
    baseline is still 20 frames in a row as read, not the indices under 20,
    and the stride starts past it (#117)."""
    loop = _live(monkeypatch, _Losing(after=10, lost=100, interval=0.002))
    indices = [l.index for l in loop.looks(200, stride=3, baseline_frames=20)]
    assert indices[:20] == list(range(11)) + list(range(111, 120))
    assert indices[20:] and all(i % 3 == 0 for i in indices[20:])


def test_live_times_are_the_stream_timestamps_from_frame_0s_wall_clock(
        monkeypatch, capsys):
    """Frames read every 2 ms, far ahead of their timestamps' 40 ms, as a
    backlog is read at startup: a Bullet Hole is timed when the stream says
    its first frame came, 1/25 s a frame after frame 0, not when it was
    read (#117)."""
    loop = _live(monkeypatch, _FakeStream(interval=0.002))
    loop.model = _Watching(lambda i: i >= 6, stop_at=120)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    monkeypatch.setattr(nbh.board, "changed_regions", lambda a, b: np.ones((64, 64), bool))
    run = nbh.process("rtsp://mtx:8554/cam", None, None, "model.pt", stride=1)
    (hole,) = run.holes
    at = nbh._clock(loop.source.times[0] + hole["first_frame"] / 25)
    new = [l for l in capsys.readouterr().out.splitlines() if l.startswith("[NEW]")]
    assert len(new) == 1 and f"t={at}" in new[0]


def test_a_reconnect_starts_a_session_indexed_by_its_own_timestamps(monkeypatch, capsys):
    """Down after frame 40, at 1.6 s of stream; the reopened session's
    timestamps restart lower, at 0.92 s, and it loses 5 frames of its own
    later. Indices carry on from #84's count of the frames the drop missed,
    and the new session is indexed from its own first frame (#117)."""
    after = _Losing(after=30, lost=5, interval=0.002)
    after.at = 22   # its first frame is 23: 920 ms
    loop = _live(monkeypatch, _FakeStream(n=40, interval=0.002), lambda: after)
    monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.1)
    indices = [l.index for l in loop.looks(80, stride=1, baseline_frames=80)]
    (_, missed), = loop.source.drops
    back = 41 + missed
    assert indices == list(range(41)) + list(range(back, back + 8)) + list(range(back + 13, 80))
    assert loop.source.unseen == list(range(41, back)) + list(range(back + 8, back + 13))
    assert loop.source.upstream == [(5, 5)] and loop.source.untimed == 0


# --- publishing Confirmed Bullet Holes (#152, #155) ---------------------------


def test_a_live_bullet_hole_is_published_at_the_time_printed_for_it_after_a_reconnect(
        monkeypatch):
    """Down after frame 40, and the Bullet Hole first seen past the reconnect.
    It is published timed as `[NEW]` prints it, by the stream's own time for
    its first frame, not frame 0's plus its index at 25 fps: past a drop the
    index is #84's wall-clock count, 1.2 s long on the replay (#152)."""
    posted = []
    after = _FakeStream(interval=0.002)
    after.at = 100   # its pixels, which `_Watching` goes by, start at 101
    loop = _live(monkeypatch, _FakeStream(n=40, interval=0.002), lambda: after)
    loop.model = _Watching(lambda i: i > 100, stop_at=200)
    monkeypatch.setattr(nbh.RegisteredFrames, "open", lambda *args: loop)
    monkeypatch.setattr(nbh.board, "changed_regions", lambda a, b: np.ones((64, 64), bool))
    run = nbh.process("rtsp://mtx:8554/cam", None, None, "model.pt", stride=1,
                      publish=posted.append)
    assert [v.first_frame for v in posted] == [h["first_frame"] for h in run.holes]
    (value,) = posted
    assert value.first_frame > 40
    assert value.first_seen_at == datetime.fromtimestamp(
        loop.source.times[value.first_frame], timezone.utc)


def test_a_recording_publishes_each_bullet_hole_at_ref_time_plus_its_time_in_the_recording(
        monkeypatch):
    """`--ref-time` is the wall clock at the Recording's t=0: from 10 s, a Bullet
    Hole first seen on frame 13 is published 10.52 s past it (#152), at the
    end of the run, where the report placed it, and in UTC whatever offset
    `--ref-time` was given in (#155)."""
    posted = []
    ref = datetime(2026, 10, 11, 13, 30, tzinfo=timezone(timedelta(hours=3)))
    def opened(video, start, model_path, conf, template_path, ref_time):
        loop = _loop(frames=100, source=nbh.Recording(_FakeCap(100), 25.0, start, ref_time))
        loop.model = _SeenOn(lambda i: i >= 6)
        return loop
    monkeypatch.setattr(nbh.RegisteredFrames, "open", opened)
    monkeypatch.setattr(nbh.board, "changed_regions", lambda a, b: np.zeros((8, 8), bool))
    run = nbh.process("clip.mp4", 10.0, 10.0 + (13 + nbh.PERSIST_FRAMES + 0.5) / 25,
                      "model.pt", require_change_evidence=False, stride=13,
                      publish=posted.append, ref_time=ref)
    assert [v.first_frame for v in posted] == [h["first_frame"] for h in run.holes] == [13]
    (value,) = posted
    assert value.first_seen_at == ref + timedelta(seconds=10.52)
    assert value.first_seen_at.tzinfo == timezone.utc
    # Board space is the template here (`_FakeView`), and every Bullet Hole a Miss.
    assert value.template_xy == (15.0, 15.0)
    assert value.target is None and value.mm is None
