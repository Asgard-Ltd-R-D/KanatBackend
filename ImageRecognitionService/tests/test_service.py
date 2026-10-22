"""Checks for the Detection Service's control API (#223), driven over HTTP
in-process: a fake Stream behind the opener, a fake detector (the live tests'
`_Marking`), and the backend replaced at the publisher's HTTP call."""
import contextlib
import json
import sys
import threading
import time
import types
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest

from detection import service, webapp
from detection import new_bullet_holes as nbh
from test_frame_loop import _FakeStream, _Marking, _openable, _Scripted

SESSION = "6f1c0d3e-2b7a-4c1e-9d3f-0a1b2c3d4e5f"
OTHER = "0b9e8d7c-6a5f-4e3d-8c2b-1a0f9e8d7c6b"
URL = "rtsp://127.0.0.1:8554/cam"


class _Api:
    """The control API on an ephemeral port, its Runs opened on an endless
    fake Stream unless `opener` is replaced and looked at by `model`, by
    default `_Marking`, and the bullets it posts in `sent`, their bodies in
    `posted`. `call` answers (status, JSON body)."""
    def __init__(self, monkeypatch, model=None):
        _openable(monkeypatch)
        monkeypatch.setattr(nbh, "Registration",
                            lambda view, base, mask, when: _Scripted(view, lambda i: True))
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


@pytest.fixture
def late(monkeypatch):
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
    assert api.call("GET", "/status") == (200, {"run": run})


def test_a_repeat_start_for_the_session_is_answered_with_its_run(api):
    """The backend's reconcile repeats a start safely: the Run is the one
    already watching, not a second one with a fresh baseline."""
    _, run = api.start()
    assert api.start() == (200, run)
    assert api.opened == [URL]


def test_a_start_for_another_session_is_refused_while_a_run_is_active(api):
    _, run = api.start()
    status, body = api.start(OTHER)
    assert (status, body["run"]) == (409, run)
    assert api.call("GET", "/status") == (200, {"run": run})


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
    opening, stream = threading.Event(), api.opener
    api.opener = lambda *args: (opening.wait(10), stream(*args))[1]
    starting = threading.Thread(target=api.start)
    starting.start()
    assert _until(lambda: _status(api))["state"] == "starting"
    opening.set()
    starting.join(10)
    assert _status(api)["state"] == "watching"


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
    assert ended == [(200, {"session_id": SESSION, "state": "ended"})]
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
    """Start a Run on `late`'s model, and end it while the Bullet Hole's
    Candidate is open: answered with the end's answer, once it returns."""
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


def test_a_bullet_hole_first_seen_just_before_the_end_is_posted_before_it_returns(late):
    """Judged as at any Look once its persistence window has elapsed, and
    posted, before the end is answered (#228): the last shot is not lost."""
    assert _end_just_after_a_shot(late) == [(200, {"session_id": SESSION, "state": "ended"})]
    assert [p["position"] for p in late.posted] == [{"x": 15.0, "y": 15.0}]


def test_a_bullet_hole_first_seen_while_the_run_is_ending_is_never_posted(late):
    """No Candidate opens while ending: the one at (55, 55) is not posted,
    though seen on every look to the end."""
    _end_just_after_a_shot(late)
    assert {"x": 55.0, "y": 55.0} not in [p["position"] for p in late.posted]


def test_an_end_returns_within_one_persistence_window_of_stream(late):
    """The Run looks on to the look that judges the last Candidate open when
    the end came, and no further: none first seen while ending holds it."""
    _end_just_after_a_shot(late)
    model = late.model
    past = [i for i in model.looks if i + 1 >= model.first + nbh.PERSIST_FRAMES]
    assert past == [model.looks[-1]]


def test_an_end_whose_stream_stops_giving_frames_returns_by_its_timeout(monkeypatch, late):
    """The Stream runs out with the Candidate still open, and never comes
    back: the Run stops past ENDING_TIMEOUT_S, its Candidate unconfirmable."""
    monkeypatch.setattr(service, "ENDING_TIMEOUT_S", 0.3)
    late.opener = lambda url, start, ref_time: (
        nbh.Stream(_FakeStream(n=150, interval=0.002), time.time(), lambda: _FakeStream(n=0)),
        np.zeros((8, 8, 3), np.int64))
    assert _end_just_after_a_shot(late) == [(200, {"session_id": SESSION, "state": "ended"})]
    assert late.posted == [] and _status(late) is None


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
