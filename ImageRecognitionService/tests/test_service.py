"""Checks for the Detection Service's control API (#223), driven over HTTP
in-process: a fake Stream behind the opener, a fake detector (the live tests'
`_Marking`), and the backend replaced at the publisher's HTTP call."""
import contextlib
import json
import math
import sys
import threading
import time
import types
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest

from detection import board, service, webapp
from detection import new_bullet_holes as nbh
from test_frame_loop import _FakeStream, _FakeView, _Marking, _openable, _Scripted

SESSION = "6f1c0d3e-2b7a-4c1e-9d3f-0a1b2c3d4e5f"
OTHER = "0b9e8d7c-6a5f-4e3d-8c2b-1a0f9e8d7c6b"
URL = "rtsp://127.0.0.1:8554/cam"


# A baseline frame's time, and where the fake Target's ring centre is in its
# 192x108 picture
ARRIVED = datetime(2026, 10, 22, 10, 15, 2, 120000, timezone.utc)
RING_AT = (120.0, 50.0)


def _traced(centre, radius, n):
    """A round Target's outline as a contour found in a frame traces it:
    `n` points, stepped a frame px, here 3 template px, either side of it."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = radius + np.where(np.arange(n) % 2, 3.0, -3.0)
    return np.stack([centre[0] + r * np.cos(a), centre[1] + r * np.sin(a)], 1)


class _Placed(_FakeView):
    """Board space with geometry: the artwork shown at a tenth of its size,
    its ring centre at RING_AT, and two Targets. Board space is template
    coordinates here: the artwork's own Target, traced in 720 points, and a
    square one to its right."""
    H = np.array([[0.1, 0.0, RING_AT[0] - 0.1 * board.RING_CENTRE_TPL[0]],
                  [0.0, 0.1, RING_AT[1] - 0.1 * board.RING_CENTRE_TPL[1]],
                  [0.0, 0.0, 1.0]])
    targets = [p.reshape(-1, 1, 2).astype(np.float32) for p in (
        _traced(board.RING_CENTRE_TPL, 500.0, 720),
        np.array([[1500.0, 100.0], [2900.0, 100.0], [2900.0, 1000.0], [1500.0, 1000.0]]))]


def _shifted(index):
    """`_Placed`'s template_to_picture, the Board moved `index` px right."""
    return np.array([[1.0, 0.0, index], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]) @ _Placed.H


class _Creeping(_Scripted):
    """A `Registration` as the camera creeps: frame i registers with the
    Board i picture px right of where `_Placed` has it, until frame
    `lost_from`, and every Look from it on is Lost. `calls` is each frame
    handed to it, `(index, pixels)`."""
    def __init__(self):
        super().__init__(_Placed(), lambda index: index < self.lost_from)
        self.lost_from = math.inf

    def register(self, frame, index):
        view = super().register(frame, index)
        if view is not None:
            view.H = _shifted(index)
        return view


class _Api:
    """The control API on an ephemeral port, its Runs opened on an endless
    fake Stream unless `opener` is replaced, onto Board space `_Placed`,
    registered by `registration`, a `_Creeping` all its Runs share, and
    looked at by `model`, by default `_Marking`, and the bullets it posts in
    `sent`, their bodies in `posted`. `call` answers (status, JSON body)."""
    def __init__(self, monkeypatch, model=None):
        _openable(monkeypatch)
        monkeypatch.setattr(nbh.board, "build_view", lambda frame, mask: (_Placed(), 0.95))
        self.registration = _Creeping()
        monkeypatch.setattr(nbh, "Registration", lambda view, base, mask, when: self.registration)
        monkeypatch.setattr(nbh, "RECONNECT_EVERY_S", 0.01)
        monkeypatch.setattr(nbh.board, "changed_regions", lambda a, b: np.ones((64, 64), bool))
        self.sent, self.posted, self.opened, self.posting = [], [], [], threading.Event()
        self.posting.set()
        monkeypatch.setattr(webapp, "urlopen", self._backend)
        self.model = model or _Marking()
        self.opener = self._stream
        self.service = service.DetectionService(self.model, "http://backend",
                                                lambda *args: self.opener(*args))
        self.server = service.serve(self.service, 0)
        threading.Thread(target=self.server.serve_forever, args=(0.01,), daemon=True).start()

    def _stream(self, url, start, ref_time):
        self.opened.append(url)
        frame0 = np.zeros((8, 8, 3), np.int64)   # pixels are the index: frame 0
        return nbh.Stream(_FakeStream(interval=0.002), time.time(),
                          lambda: _FakeStream(n=0)), frame0

    def _backend(self, request, timeout):
        assert self.posting.wait(10)
        self.sent.append(request.full_url)
        self.posted.append(json.loads(request.data))
        return contextlib.nullcontext(types.SimpleNamespace(status=201))

    def call(self, method, path, body=None):
        """`body` is sent as JSON, or as it is when it is bytes."""
        data = body if body is None or isinstance(body, bytes) else json.dumps(body).encode()
        request = Request(f"http://127.0.0.1:{self.server.server_address[1]}{path}",
                          data=data, method=method)
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b"null")
        except HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    def start(self, session_id=SESSION, url=URL):
        return self.call("POST", "/runs", {"session_id": session_id, "stream_url": url})

    def close(self):
        self.posting.set()
        self.service.close()
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def api(monkeypatch):
    api = _Api(monkeypatch)
    yield api
    api.close()


def _still(run):
    """`run` less what moves on with each Look: `registered` and `looked_at`."""
    return {k: v for k, v in run.items() if k not in ("registered", "looked_at")}


@pytest.fixture
def placed(api):
    """`api`, its Runs' baseline frame 192x108 and read at ARRIVED."""
    api.opener = lambda url, start, ref_time: (
        nbh.Stream(_FakeStream(interval=0.002), ARRIVED.timestamp(), lambda: _FakeStream(n=0)),
        np.zeros((108, 192, 3), np.int64))
    return api


@pytest.fixture
def shot_before_end(monkeypatch):
    """`api`, its Runs looked at by `_ShotBeforeEnd`."""
    api = _Api(monkeypatch, _ShotBeforeEnd())
    yield api
    api.close()


def test_a_start_is_answered_once_the_run_is_watching(api):
    """Answered with the Baseline Marks counted: the baseline is built, so
    the Run is watching from then (`_Marking` leaves one on every frame)."""
    status, run = api.start()
    assert status == 200
    assert (run["session_id"], run["state"], run["baseline_marks"]) == (SESSION, "watching", 1)
    assert api.opened == [URL]
    assert _still(_status(api)) == _still(run)


def test_a_repeat_start_for_the_session_is_answered_with_its_run(api):
    """The backend's reconcile repeats a start safely: the Run is the one
    already watching, not a second one with a fresh baseline."""
    _, run = api.start()
    status, again = api.start()
    assert (status, _still(again)) == (200, _still(run))
    assert api.opened == [URL]


def test_a_start_for_another_session_is_refused_while_a_run_is_active(api):
    _, run = api.start()
    status, body = api.start(OTHER)
    assert (status, _still(body["run"])) == (409, _still(run))
    assert _still(_status(api)) == _still(run)


def _cannot_open(monkeypatch, api):
    """The command line's Stream, on a capture whose first read fails, as one
    that does not open within STREAM_TIMEOUT_MS does."""
    monkeypatch.setattr(nbh, "_open_stream", lambda url: types.SimpleNamespace(
        read=lambda: (False, None)))
    api.opener = nbh.Stream.open


def _no_target(monkeypatch, api):
    monkeypatch.setattr(nbh.board, "build_view", lambda frame, mask: (None, 0.0))


@pytest.mark.parametrize("failing, reason", [
    (_cannot_open, f"cannot read {URL}"),
    (_no_target, "no Target found in the baseline frame; cannot locate the Board")])
def test_a_run_that_cannot_start_fails_with_its_reason_and_leaves_no_run(
        monkeypatch, api, failing, reason):
    failing(monkeypatch, api)
    assert api.start() == (502, {"detail": reason})
    assert api.call("GET", "/status") == (200, {"run": None})


def _until(answer, timeout=10):
    """`answer()`, asked until it is truthy."""
    deadline = time.monotonic() + timeout
    while not (value := answer()):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    return value


def _status(api):
    return api.call("GET", "/status")[1]["run"]


def test_status_reports_a_run_starting_until_it_is_watching(api):
    """With no Baseline View, `registered` or `looked_at` until then: no
    baseline frame has placed the Board on the picture yet (ADR-0009)."""
    opening, stream = threading.Event(), api.opener
    api.opener = lambda *args: (opening.wait(10), stream(*args))[1]
    starting = threading.Thread(target=api.start)
    starting.start()
    run = _until(lambda: _status(api))
    assert (run["state"], run["baseline_view"], run["registered"], run["looked_at"]) == (
        "starting", None, None, None)
    opening.set()
    starting.join(10)
    run = _status(api)
    assert run["state"] == "watching"
    assert None not in (run["baseline_view"], run["registered"], run["looked_at"])


def test_a_watching_runs_baseline_view_places_the_artwork_on_its_picture(placed):
    """The artwork's ring centre goes through `template_to_picture` onto the
    fake Target's place in the baseline frame, timed on first_seen_at's clock."""
    _, run = placed.start()
    view = run["baseline_view"]
    assert view["taken_at"] == "2026-10-22T10:15:02.120+00:00"
    assert view["picture"] == {"width": 192, "height": 108}
    ring = board.apply(np.array(view["template_to_picture"]), [board.RING_CENTRE_TPL])[0]
    assert ring == pytest.approx(RING_AT, abs=1e-3)
    assert _status(placed)["baseline_view"] == view


def test_a_baseline_view_has_one_outline_per_target_in_target_order(placed):
    """Each outline in template coordinates, cut to at most OUTLINE_POINTS
    of its own points: the round one keeps to its radius, and the square
    keeps its corners."""
    round_one, square = placed.start()[1]["baseline_view"]["targets"]
    assert 8 <= len(round_one) <= service.OUTLINE_POINTS
    radii = np.linalg.norm(np.array(round_one) - board.RING_CENTRE_TPL, axis=1)
    assert radii == pytest.approx(500.0, abs=3.1)
    assert sorted(map(tuple, square)) == [(1500.0, 100.0), (1500.0, 1000.0),
                                          (2900.0, 100.0), (2900.0, 1000.0)]


def test_a_baseline_views_marks_lie_where_the_fake_detector_planted_them(monkeypatch, placed):
    """In template coordinates: `_Marking`'s mark at (40, 40) in a Board
    space drawn at twice the template's scale is at (20, 20) on it."""
    class Doubled(_Placed):
        tpl_to_board = np.diag([2.0, 2.0, 1.0])
    monkeypatch.setattr(nbh.board, "build_view", lambda frame, mask: (Doubled(), 0.95))
    assert placed.start()[1]["baseline_view"]["baseline_marks"] == [[20.0, 20.0]]


def _frame(at):
    """The index of the `placed` Stream's frame timed `at`: one each
    1/LIVE_FPS s from ARRIVED."""
    return round((datetime.fromisoformat(at) - ARRIVED).total_seconds() * nbh.LIVE_FPS)


def _ring(registered):
    """Where `registered` places the artwork's ring centre in the picture."""
    return board.apply(np.array(registered["template_to_picture"]), [board.RING_CENTRE_TPL])[0]


def test_registered_follows_the_board_as_it_moves_in_the_picture(placed):
    """Each read carries the latest registered Look: its frame's time, and
    where it placed the Board, a picture px further right each frame."""
    placed.start()
    first = _status(placed)["registered"]
    later = _until(lambda: (r := _status(placed)["registered"]) != first and r)
    assert _frame(later["at"]) > _frame(first["at"])
    for registered in (first, later):
        assert _ring(registered) == pytest.approx(
            (RING_AT[0] + _frame(registered["at"]), RING_AT[1]), abs=1e-3)


def test_a_lost_look_leaves_registered_as_it_was_while_looked_at_moves_on(placed):
    placed.registration.lost_from = 100
    placed.start()
    run = _until(lambda: (r := _status(placed))["looked_at"] and _frame(r["looked_at"]) >= 100 and r)
    later = _until(lambda: (r := _status(placed))["looked_at"] != run["looked_at"] and r)
    assert _frame(run["registered"]["at"]) < 100
    assert later["registered"] == run["registered"]
    assert _frame(later["looked_at"]) > _frame(run["looked_at"])


def test_an_ends_answer_carries_the_runs_final_registered_and_looked_at(placed):
    """Its last Look's time, Lost here, and the last registered one's, not
    those of the last read before the end."""
    placed.registration.lost_from = 100
    placed.start()
    _until(lambda: _frame(_status(placed)["looked_at"]) >= 100)
    answer = placed.call("POST", f"/runs/{SESSION}/end")
    looks = [index for index, _ in placed.registration.calls]
    assert _ends([answer]) == [ENDED]
    _, ended = answer
    assert _frame(ended["looked_at"]) == looks[-1]
    assert _frame(ended["registered"]["at"]) == max(i for i in looks if i < 100)
    assert _ring(ended["registered"]) == pytest.approx(
        (RING_AT[0] + _frame(ended["registered"]["at"]), RING_AT[1]), abs=1e-3)


def test_an_end_is_answered_once_the_runs_posts_are_drained(api):
    """The backend holds the Run's one post, its Bullet Hole from frame 6,
    until let go: meanwhile the Run is `ending` and the end unanswered."""
    api.posting.clear()
    api.start()
    assert api.model.past.wait(10)   # its persistence window has elapsed
    ended = []
    ending = threading.Thread(
        target=lambda: ended.append(api.call("POST", f"/runs/{SESSION}/end")))
    ending.start()
    ending.join(0.3)
    assert ending.is_alive() and _status(api)["state"] == "ending"
    api.posting.set()
    ending.join(10)
    assert _ends(ended) == [ENDED]
    assert api.sent == [f"http://backend/sessions/{SESSION}/bullets"]
    assert _status(api) is None


class _ShotBeforeEnd:
    """A Baseline Mark at (40, 40) on every frame, and a Bullet Hole at
    (15, 15) from frame 100. The look after the one that first saw it sets
    `seen` and waits for `go`, so an end asked for meanwhile finds its
    Candidate open. From then on a second Bullet Hole, at (55, 55), is seen
    too: first seen while the Run is ending. `looks` is every frame looked at."""
    names = {0: "bullet_hole"}

    def __init__(self):
        self.seen, self.go, self.first, self.looks = threading.Event(), threading.Event(), None, []

    def predict(self, image, imgsz, conf, verbose=False, classes=None):
        index = int(image[0, 0, 0])
        self.looks.append(index)
        if index >= 100 and self.first is None:
            self.first = index
        elif self.first is not None and not self.seen.is_set():
            self.seen.set()
            assert self.go.wait(10)
        boxes = ([[35.0, 35.0, 45.0, 45.0]] + ([[10.0, 10.0, 20.0, 20.0]] if index >= 100 else [])
                 + ([[50.0, 50.0, 60.0, 60.0]] if self.go.is_set() else []))
        return [types.SimpleNamespace(boxes=[types.SimpleNamespace(xyxy=[b]) for b in boxes])]


def _end_just_after_a_shot(api):
    """Start a Run on `shot_before_end`'s model, and end it while the Bullet
    Hole's Candidate is open: answered with the end's answer, once it returns."""
    model = api.model
    api.start()
    assert model.seen.wait(10)
    ended = []
    ending = threading.Thread(
        target=lambda: ended.append(api.call("POST", f"/runs/{SESSION}/end")))
    ending.start()
    _until(lambda: _status(api)["state"] == "ending")
    model.go.set()
    ending.join(10)
    return ended


ENDED = (200, SESSION, "ended")


def _ends(answers):
    """Each end's answer as `(status, session_id, state)`."""
    return [(status, body["session_id"], body["state"]) for status, body in answers]


def test_a_bullet_hole_first_seen_just_before_the_end_is_posted_before_it_returns(
        shot_before_end):
    """Judged as at any Look once its persistence window has elapsed, and
    posted, before the end is answered (#228): the last shot is not lost."""
    assert _ends(_end_just_after_a_shot(shot_before_end)) == [ENDED]
    assert [p["position"] for p in shot_before_end.posted] == [{"x": 15.0, "y": 15.0}]


def test_a_bullet_hole_first_seen_while_the_run_is_ending_is_never_posted(shot_before_end):
    """No Candidate opens while ending: the one at (55, 55) is not posted,
    though seen on every look to the end."""
    _end_just_after_a_shot(shot_before_end)
    assert {"x": 55.0, "y": 55.0} not in [p["position"] for p in shot_before_end.posted]


def test_an_end_returns_within_one_persistence_window_of_stream(shot_before_end):
    """The Run looks on to the look that judges the last Candidate open when
    the end came, and no further: none first seen while ending holds it."""
    _end_just_after_a_shot(shot_before_end)
    model = shot_before_end.model
    past = [i for i in model.looks if i + 1 >= model.first + nbh.PERSIST_FRAMES]
    assert past == [model.looks[-1]]


def test_an_end_whose_stream_stops_giving_frames_returns_by_its_timeout(
        monkeypatch, shot_before_end):
    """The Stream runs out with the Candidate still open, and never comes
    back: the Run stops past ENDING_TIMEOUT_S, its Candidate unconfirmable."""
    monkeypatch.setattr(service, "ENDING_TIMEOUT_S", 0.3)
    shot_before_end.opener = lambda url, start, ref_time: (
        nbh.Stream(_FakeStream(n=150, interval=0.002), time.time(), lambda: _FakeStream(n=0)),
        np.zeros((8, 8, 3), np.int64))
    assert _ends(_end_just_after_a_shot(shot_before_end)) == [ENDED]
    assert shot_before_end.posted == [] and _status(shot_before_end) is None


@pytest.mark.parametrize("session_id", [SESSION, OTHER, "not-a-uuid"])
def test_ending_a_run_that_does_not_exist_answers_404(api, session_id):
    if session_id == OTHER:
        api.start()   # SESSION's Run, not this one
    assert api.call("POST", f"/runs/{session_id}/end") == (404, {"detail": "no such Run"})


def test_consecutive_runs_share_the_detector_loaded_once(monkeypatch, api):
    """Each Run opens on the service's detector: none loads its own, and a
    Session's Run can start once the one before has ended."""
    monkeypatch.setitem(sys.modules, "ultralytics", None)   # any model load would fail
    for session_id in (SESSION, OTHER):
        assert api.start(session_id)[1]["state"] == "watching"
        assert api.call("POST", f"/runs/{session_id}/end")[0] == 200
    assert api.opened == [URL, URL]


def test_the_control_api_answers_on_the_loopback_only(api):
    assert api.server.server_address[0] == "127.0.0.1"


@pytest.mark.parametrize("body", [
    b"not json", b"[]", json.dumps({"session_id": SESSION}).encode(),
    json.dumps({"session_id": "not-a-uuid", "stream_url": URL}).encode(),
    json.dumps({"session_id": SESSION, "stream_url": "http://127.0.0.1/cam"}).encode()])
def test_a_start_without_a_sessions_uuid_and_an_rtsp_url_is_refused(api, body):
    assert api.call("POST", "/runs", body)[0] == 400
    assert _status(api) is None and api.opened == []


def test_a_start_whose_run_is_ended_before_it_is_watching_is_refused(api):
    """An end while the Stream opens: the start is answered 409 with the
    Run `ending`, never as watching."""
    opening, stream = threading.Event(), api.opener
    api.opener = lambda *args: (opening.wait(10), stream(*args))[1]
    answers = []
    starting = threading.Thread(target=lambda: answers.append(api.start()))
    starting.start()
    _until(lambda: _status(api))
    ending = threading.Thread(target=api.call, args=("POST", f"/runs/{SESSION}/end"))
    ending.start()
    _until(lambda: _status(api)["state"] == "ending")
    opening.set()
    starting.join(10)
    ending.join(10)
    ((status, body),) = answers
    assert (status, body["run"]["state"]) == (409, "ending")
    assert _status(api) is None


def test_a_run_not_watching_within_the_start_timeout_is_ended_and_fails(monkeypatch, api):
    """Frame 0 arrives and then nothing, so the baseline is never built and
    the Stream reconnects for good: the start fails past START_TIMEOUT_S,
    and the Run is ended rather than left holding the one Run."""
    monkeypatch.setattr(service, "START_TIMEOUT_S", 0.3)
    api.opener = lambda url, start, ref_time: (
        nbh.Stream(_FakeStream(n=0), time.time(), lambda: _FakeStream(n=0)),
        np.zeros((8, 8, 3), np.int64))
    assert api.start() == (502, {"detail": "not watching within 0.3 s: no baseline was built"})
    assert _status(api) is None
