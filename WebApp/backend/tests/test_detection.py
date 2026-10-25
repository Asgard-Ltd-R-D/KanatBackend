"""A Session with a camera is watched by a Run of the Detection Service
(ADR-0008), driven through the REST API with the database replaced and the
Detection Service faked at its client module; and that client's reading of
the service's answers."""
import json
import uuid
from contextlib import contextmanager
from datetime import datetime

import anyio
import httpx
import pytest

from app.core.live import hub
from app.repositories import bullets as bullets_repo
from app.repositories import sessions as sessions_repo
from app.services import detection_client, detection_sync
from app.services import recordings as recording_svc
from app.services import sessions as sessions_svc
from tests.fakes import NOW, FakeDB, baseline_view, make_camera, place


def add_camera(db, alias="lane1", enabled=True):
    camera = make_camera(alias, enabled=enabled)
    db.cameras[camera.id] = camera
    return camera


@pytest.fixture
def streams(detection):
    """Each Session's live stream by its id, subscribed when its Run is asked
    for: as the frontend listens once the create call has answered."""
    subscribed = {}
    detection.on_start = lambda session_id: subscribed.setdefault(session_id, hub.subscribe(session_id))
    yield subscribed
    for session_id, queue in subscribed.items():
        hub.unsubscribe(session_id, queue)


def events(queue):
    out = []
    while not queue.empty():
        out.append(json.loads(queue.get_nowait()))
    return out


@contextmanager
def listening(session_id):
    """The Session's live stream, for as long as the block runs."""
    queue = hub.subscribe(session_id)
    try:
        yield queue
    finally:
        hub.unsubscribe(session_id, queue)


def start_session(client, camera):
    return uuid.UUID(client.post("/sessions", json={"name": "Range 1", "camera_id": str(camera.id)}).json()["id"])


def detection_of(client, session_id):
    return client.get(f"/sessions/{session_id}").json()["detection"]


def tick(client):
    """One round of the loop that reconciles the Detection Service's Run, on a
    worker thread of the app's event loop as the loop runs it."""
    client.portal.call(anyio.to_thread.run_sync, detection_sync.reconcile, FakeDB())


def not_watching(reason):
    return {"state": "not_watching", "reason": reason, "detail": None}


WATCHING = {"state": "watching", "reason": None, "detail": None}


# --- starting ---

def test_a_session_with_a_camera_asks_for_a_run_on_its_stream(client, db, detection):
    camera = add_camera(db)

    res = client.post("/sessions", json={"name": "Range 1", "camera_id": str(camera.id)})

    assert res.status_code == 201
    assert res.json()["camera_id"] == str(camera.id)
    assert detection.calls == [("start", uuid.UUID(res.json()["id"]), "rtsp://127.0.0.1:8554/lane1")]


def test_a_session_without_a_camera_asks_for_nothing(client, db, detection):
    res = client.post("/sessions", json={"name": "Range 1"})

    assert res.json()["camera_id"] is None
    assert res.json()["detection"] == {"state": "none", "reason": None, "detail": None}
    assert detection.calls == []


@pytest.mark.parametrize("enabled", [True, False])
def test_a_session_needs_an_enabled_camera_that_exists(client, db, detection, enabled):
    camera = add_camera(db, enabled=False)
    camera_id = camera.id if not enabled else uuid.uuid4()

    res = client.post("/sessions", json={"name": "Range 1", "camera_id": str(camera_id)})

    assert res.status_code == 422
    assert db.sessions == {} and detection.calls == []


def test_the_camera_cannot_be_changed_after_creation(client, db, detection):
    camera, other = add_camera(db), add_camera(db, "lane2")
    session_id = client.post("/sessions", json={"name": "Range 1", "camera_id": str(camera.id)}).json()["id"]

    res = client.patch(f"/sessions/{session_id}", json={"camera_id": str(other.id)})

    assert res.status_code == 422
    assert client.get(f"/sessions/{session_id}").json()["camera_id"] == str(camera.id)


def test_the_session_is_starting_then_watching_and_says_so_live(client, db, detection, streams):
    res = client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)})

    # Answered at once, before the Run is watching
    assert res.json()["detection"]["state"] == "starting"
    assert events(streams[uuid.UUID(res.json()["id"])]) == [
        {"type": "detection_updated", "detection": {"state": "watching", "reason": None, "detail": None}},
    ]
    assert client.get(f"/sessions/{res.json()['id']}").json()["detection"]["state"] == "watching"


@pytest.mark.parametrize("error, reason, detail", [
    (detection_client.RunRefused(502, "no Target on the baseline frame"), "stream_failed", "no Target on the baseline frame"),
    (detection_client.RunRefused(409, "another Session's Run is active"), "other_session", "another Session's Run is active"),
    (detection_client.DetectionServiceUnreachable("connection refused"), "service_down", None),
])
def test_a_start_that_fails_reads_not_watching_with_its_reason(client, db, detection, streams, error, reason, detail):
    detection.start_error = error

    session_id = client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)}).json()["id"]

    expected = {"state": "not_watching", "reason": reason, "detail": detail}
    assert events(streams[uuid.UUID(session_id)]) == [{"type": "detection_updated", "detection": expected}]
    assert client.get(f"/sessions/{session_id}").json()["detection"] == expected


# --- ending ---

def test_completing_a_session_ends_its_run_before_it_reads_completed(client, db, detection):
    session_id = client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)}).json()["id"]
    status_at_end = []
    detection.on_end = lambda sid: status_at_end.append(db.sessions[sid].status)
    stream = hub.subscribe(uuid.UUID(session_id))
    try:
        res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})
        seen = [(e["type"], e.get("detection", {}).get("state") or e.get("status")) for e in events(stream)]
    finally:
        hub.unsubscribe(uuid.UUID(session_id), stream)

    assert status_at_end == ["active"]       # its last posts are still stored
    assert res.json()["status"] == "completed"
    assert res.json()["detection"]["state"] == "none"
    assert seen == [
        ("detection_updated", "ending"),
        ("detection_updated", "none"),
        ("session_updated", "completed"),
    ]


def test_completing_a_session_without_a_camera_ends_nothing(client, db, detection):
    session_id = client.post("/sessions", json={"name": "Range 1"}).json()["id"]

    assert client.patch(f"/sessions/{session_id}", json={"status": "completed"}).json()["status"] == "completed"
    assert detection.calls == []


def test_a_bullet_hole_posted_during_the_end_window_is_stored(client, db, detection, monkeypatch):
    # The Run judges its open Candidates before its end is answered, and
    # posts what persisted meanwhile
    stored = []

    def add(db, bullet):
        bullet.created_at = NOW
        stored.append(bullet)
        return bullet

    monkeypatch.setattr(bullets_repo, "find_by_idempotency_key", lambda db, session_id, key: None)
    monkeypatch.setattr(bullets_repo, "count_active", lambda db, session_id: len(stored))
    monkeypatch.setattr(bullets_repo, "add", add)
    session_id = start_session(client, add_camera(db))
    posted = []
    detection.on_end = lambda sid: posted.append(client.post(f"/sessions/{sid}/bullets", json={
        "version": "v1", "first_seen_at": NOW.isoformat(), "position": {"x": 100, "y": 200}}).status_code)

    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert posted == [201]
    assert [b.session_id for b in stored] == [session_id]


END_UNCONFIRMED = {"state": "end_unconfirmed", "reason": None, "detail": None}


def test_completing_still_succeeds_when_the_detection_service_is_down(client, db, detection):
    # Or does not answer in time: the client raises the same for both
    session_id = client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)}).json()["id"]

    def down(session_id):
        raise detection_client.DetectionServiceUnreachable("connection refused")

    detection.on_end = down

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    tick(client)

    assert res.json()["status"] == "completed"
    # The page says so, and keeps saying it: its last Bullet Holes may be missing
    assert res.json()["detection"] == END_UNCONFIRMED
    assert detection_of(client, session_id) == END_UNCONFIRMED


def test_a_watched_session_whose_run_is_already_gone_reads_end_unconfirmed(client, db, detection):
    # Lost since the last tick, which still read watching: the 404 for no such
    # Run does not say what it saw last was posted
    session_id = start_session(client, add_camera(db))
    detection.run = None

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert res.json()["detection"] == END_UNCONFIRMED


def test_a_watched_session_read_not_watching_since_reads_end_unconfirmed(client, db, detection):
    # A tick while the Detection Service was down read it service_down: its
    # Run may still hold its last shots
    session_id = start_session(client, add_camera(db))
    detection.down = True
    tick(client)

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert res.json()["detection"] == END_UNCONFIRMED


def test_a_session_whose_run_ended_while_it_was_active_reads_none(client, db, detection):
    # Its camera disabled: the Run's end was confirmed while the Session still
    # stored what it posted
    camera = add_camera(db)
    session_id = start_session(client, camera)
    camera.enabled = False
    tick(client)

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert res.json()["detection"]["state"] == "none"


def test_a_run_another_end_confirmed_meanwhile_leaves_the_end_confirmed(client, db, detection):
    # A tick, its camera disabled, ended the Run while the Session was still
    # active, just before this end reached the Detection Service: no such Run
    session_id = start_session(client, add_camera(db))
    run, detection.run = detection.run, None

    def ended_by_a_tick(sid):
        detection.on_end = lambda sid: None
        detection.run = run
        detection_sync._end_run(sid)

    detection.on_end = ended_by_a_tick

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert res.json()["detection"]["state"] == "none"


def test_a_session_no_run_watched_reads_none_however_its_end_went(client, db, detection):
    # Its Run never started: nothing of its own was in flight
    detection.start_error = detection_client.RunRefused(502, "no Target on the baseline frame")
    waiting = start_session(client, add_camera(db))
    detection.down = True

    res = client.patch(f"/sessions/{waiting}", json={"status": "completed"})

    assert res.json()["detection"]["state"] == "none"


def test_completing_ends_the_run_of_a_session_whose_camera_was_deleted(client, db, detection):
    session_id = client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)}).json()["id"]
    db.sessions[uuid.UUID(session_id)].camera_id = None   # the camera deleted: ON DELETE SET NULL

    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert detection.calls[-1] == ("end", uuid.UUID(session_id))


def test_deleting_an_active_session_ends_its_run(client, db, detection, monkeypatch):
    monkeypatch.setattr(sessions_repo, "delete", lambda _, session: db.sessions.pop(session.id))
    monkeypatch.setattr(sessions_repo, "intervals_of_other_sessions", lambda _, session_id: [])
    monkeypatch.setattr(recording_svc, "delete_session_video", lambda windows, others: 0)
    session_id = uuid.UUID(client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)}).json()["id"])

    assert client.delete(f"/sessions/{session_id}").status_code == 204
    assert detection.calls[-1] == ("end", session_id)
    assert session_id not in db.sessions


def test_a_run_that_starts_after_its_session_ended_is_ended(client, db, detection):
    # The end reached the Detection Service first and found no Run (404)
    detection.on_start = lambda session_id: client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    session_id = uuid.UUID(client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)}).json()["id"])

    assert [call[0] for call in detection.calls] == ["start", "end", "end"]
    assert client.get(f"/sessions/{session_id}").json()["detection"]["state"] == "none"


def test_a_start_answered_after_the_session_ended_changes_nothing(client, db, detection):
    # The operator ends the Session while its Run is still starting: the
    # service then refuses the start, which must not mark a completed Session
    # as not watching
    detection.start_error = detection_client.RunRefused(409, "the Session's Run is ending")
    detection.on_start = lambda session_id: client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    session_id = client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)}).json()["id"]

    assert client.get(f"/sessions/{session_id}").json()["detection"]["state"] == "none"


# --- reconciling every few seconds ---

def test_a_detection_service_back_up_with_no_run_gets_it_from_the_next_tick(client, db, detection):
    session_id = start_session(client, add_camera(db))
    with listening(session_id) as stream:
        detection.down, detection.run = True, None   # the Detection Service restarts
        tick(client)
        while_down = detection_of(client, session_id)
        detection.down = False
        tick(client)
        seen = [e["detection"] for e in events(stream)]

    assert while_down == not_watching("service_down")
    assert detection.calls[-1] == ("start", session_id, "rtsp://127.0.0.1:8554/lane1")
    assert seen == [not_watching("service_down"), WATCHING]


def test_a_run_lost_while_the_service_is_up_reads_not_watching_until_it_is_back(client, db, detection):
    session_id = start_session(client, add_camera(db))
    with listening(session_id) as stream:
        detection.run = None   # its Stream failed, or the service restarted between two ticks
        tick(client)
        seen = [e["detection"] for e in events(stream)]

    assert detection.calls[-1] == ("start", session_id, "rtsp://127.0.0.1:8554/lane1")
    assert seen == [not_watching(None), WATCHING]


def test_the_run_of_a_session_completed_while_the_service_was_down_is_ended(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection.down = True
    client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    detection.down = False

    tick(client)

    assert detection.calls[-1] == ("end", session_id)
    assert detection.run is None
    # Ended after the Session completed: what it posted on the way out was refused
    assert detection_of(client, session_id) == END_UNCONFIRMED


def test_the_run_of_a_deleted_session_is_ended(client, db, detection):
    deleted = uuid.uuid4()
    detection.run = detection_client.Run(deleted, "watching")

    tick(client)

    assert detection.calls == [("end", deleted)]


@pytest.mark.parametrize("change", ["disabled", "deleted"])
def test_a_camera_disabled_or_deleted_mid_session_ends_its_run(client, db, detection, change):
    camera = add_camera(db)
    session_id = start_session(client, camera)
    if change == "disabled":
        camera.enabled = False
    else:
        del db.cameras[camera.id]
        db.sessions[session_id].camera_id = None   # ON DELETE SET NULL

    tick(client)
    calls = list(detection.calls)
    tick(client)

    assert calls[-1] == ("end", session_id)
    assert detection.calls == calls   # and is not started again
    session = client.get(f"/sessions/{session_id}").json()
    assert (session["status"], session["detection"]) == ("active", not_watching("camera_disabled"))


@pytest.mark.parametrize("confirmed", [True, False])
def test_a_reopened_session_gets_a_new_run(client, db, detection, confirmed):
    session_id = start_session(client, add_camera(db))
    detection.down = not confirmed   # its end is not confirmed, and its Run left
    client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    detection.down = False
    tick(client)   # ends the Run of a Session no longer active
    client.patch(f"/sessions/{session_id}", json={"status": "active"})

    tick(client)

    assert detection.calls[-1] == ("start", session_id, "rtsp://127.0.0.1:8554/lane1")
    assert detection_of(client, session_id) == WATCHING


def test_after_a_backend_restart_a_watched_session_reads_watching_by_the_next_tick(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection_sync._states.clear()   # the backend restarted; its Run did not
    calls = list(detection.calls)

    tick(client)

    assert detection_of(client, session_id) == WATCHING
    assert detection.calls == calls


def test_a_session_started_during_a_tick_keeps_its_run(client, db, detection):
    # Its Run is in the Detection Service's status, so its Session is read
    camera, started = add_camera(db), []

    def start_one():
        if not started:
            started.append(start_session(client, camera))

    detection.on_status = start_one

    tick(client)

    assert detection.run[:2] == (started[0], "watching")
    assert [call[0] for call in detection.calls] == ["start"]


def test_a_second_start_for_a_watched_session_leaves_its_run(client, db, detection):
    # The create's own start and a tick's can both ask for the Run, and the
    # Detection Service answers both with the one Run
    session_id = start_session(client, add_camera(db))

    client.portal.call(anyio.to_thread.run_sync, detection_sync.watch, session_id, "lane1")

    assert detection.run[:2] == (session_id, "watching")
    assert detection_of(client, session_id) == WATCHING


def test_a_tick_while_a_session_ends_leaves_it_to_its_end(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection.on_end = lambda sid: detection_sync.reconcile(FakeDB())

    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert [call[0] for call in detection.calls] == ["start", "end"]
    assert detection_of(client, session_id)["state"] == "none"


def test_a_tick_before_a_completion_is_committed_starts_no_run(client, db, detection, monkeypatch):
    # The Run has ended, but the Session still reads active in the database
    session_id = start_session(client, add_camera(db))
    update = sessions_svc.update_session

    def tick_first(*args):
        detection_sync.reconcile(FakeDB())
        return update(*args)

    monkeypatch.setattr(sessions_svc, "update_session", tick_first)

    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert [call[0] for call in detection.calls] == ["start", "end"]
    assert detection_of(client, session_id)["state"] == "none"


def test_a_completion_that_fails_leaves_the_session_to_be_watched_again(client, db, detection, monkeypatch):
    session_id = start_session(client, add_camera(db))
    update, failing = sessions_svc.update_session, [True]

    def fail_once(*args):
        if failing.pop():
            raise RuntimeError("the database went away")
        return update(*args)

    monkeypatch.setattr(sessions_svc, "update_session", fail_once)
    with pytest.raises(RuntimeError):
        client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert detection_sync.state_of(session_id).state == "none"
    tick(client)
    assert detection.calls[-1] == ("start", session_id, "rtsp://127.0.0.1:8554/lane1")
    assert detection_of(client, session_id) == WATCHING


def test_a_start_that_fails_unexpectedly_reads_not_watching_and_is_retried(client, db, detection):
    detection.start_error = ZeroDivisionError("float division by zero")
    session_id = start_session(client, add_camera(db))

    assert detection_of(client, session_id) == not_watching(None)
    detection.start_error = None
    tick(client)
    assert detection_of(client, session_id) == WATCHING


def test_a_start_refused_for_its_own_run_still_ending_reads_no_reason(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection.run = detection.run._replace(state="starting")   # a lost Run's, still ending
    detection.start_error = detection_client.RunRefused(409, "the Session's Run is ending", session_id)
    detection_sync._states[session_id] = detection_sync.RUN_LOST

    client.portal.call(anyio.to_thread.run_sync, lambda: detection_sync.watch(session_id, "lane1", ("not_watching",)))

    assert detection_of(client, session_id) == {"state": "not_watching", "reason": None,
                                                "detail": "the Session's Run is ending"}


def test_a_start_lost_to_an_error_is_let_go_by_a_tick(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection.run = None
    client.portal.call(anyio.to_thread.run_sync, detection_sync._set, session_id, detection_sync.Detection(state="starting"))
    calls = list(detection.calls)
    tick(client)
    assert detection.calls == calls   # still under way, as far as the tick knows

    detection_sync._since[session_id] -= detection_sync.STUCK_S + 1
    tick(client)   # lets it go
    tick(client)   # and watches it again

    assert detection.calls[-1] == ("start", session_id, "rtsp://127.0.0.1:8554/lane1")
    assert detection_of(client, session_id) == WATCHING


def test_a_slow_end_is_never_let_go_while_its_completion_is_under_way(client, db, detection, monkeypatch):
    # The completion's commit hangs past STUCK_S: a tick meanwhile starts no
    # Run for the Session being completed
    session_id = start_session(client, add_camera(db))
    update = sessions_svc.update_session

    def slow(*args):
        detection_sync._since[session_id] -= detection_sync.STUCK_S + 1
        detection_sync.reconcile(FakeDB())
        detection_sync.reconcile(FakeDB())
        return update(*args)

    monkeypatch.setattr(sessions_svc, "update_session", slow)
    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert [call[0] for call in detection.calls] == ["start", "end"]
    assert detection_of(client, session_id)["state"] == "none"


def test_a_completion_that_fails_after_its_commit_still_warns_of_an_unconfirmed_end(client, db, detection, monkeypatch):
    # Its Run already gone, so its end is not confirmed; the Session is
    # completed, but reading it back fails
    session_id = start_session(client, add_camera(db))
    detection.run = None
    update = sessions_svc.update_session

    def fail_after(*args):
        update(*args)
        raise RuntimeError("the database went away")

    monkeypatch.setattr(sessions_svc, "update_session", fail_after)
    with pytest.raises(RuntimeError):
        client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert detection_of(client, session_id) == END_UNCONFIRMED


def test_a_run_already_ending_is_left_to_its_end(client, db, detection):
    # Its end blocks for up to END_TIMEOUT_S: a tick does not wait on it again
    session_id = start_session(client, add_camera(db))
    run = detection.run
    client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    detection.run = run._replace(state="ending")   # its end not answered yet
    calls = list(detection.calls)

    tick(client)

    assert detection.calls == calls


def test_a_session_no_longer_active_reads_none_by_the_next_tick(client, db, detection):
    session_id = start_session(client, add_camera(db))
    client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    # As a start that raced its end leaves it
    detection_sync._states[session_id] = detection_sync.RUN_LOST

    tick(client)

    assert detection_of(client, session_id)["state"] == "none"


def test_a_tick_with_nothing_to_change_makes_no_call_and_pushes_nothing(client, db, detection):
    session_id = start_session(client, add_camera(db))
    tick(client)
    calls = list(detection.calls)

    with listening(session_id) as stream:
        tick(client)
        pushed = events(stream)

    assert detection.calls == calls
    assert pushed == []


# --- the client ---

def test_the_client_reads_the_detection_services_answers(monkeypatch):
    answers = {}

    def request(method, url, timeout, **kwargs):
        status, body = answers[url.rsplit(":8010", 1)[1]]
        return httpx.Response(status, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr(detection_client.httpx, "request", request)
    session_id = uuid.uuid4()

    answers["/status"] = (200, {"run": None})
    assert detection_client.status() is None
    view, registered = baseline_view(NOW), place(NOW, dx=3.0)
    looked_at = "2026-10-22T09:00:05.560+00:00"
    watching = {"session_id": str(session_id), "state": "watching", "since": "2026-10-22T09:00:00+00:00",
                "baseline_marks": 3, "baseline_view": view.model_dump(mode="json"),
                "registered": registered.model_dump(mode="json"), "looked_at": looked_at}
    read = (session_id, "watching", view, registered, datetime.fromisoformat(looked_at))
    answers["/status"] = (200, {"run": watching})
    assert detection_client.status() == read
    answers["/status"] = (200, {"run": {**watching, "state": "starting", "baseline_view": None,
                                        "registered": None, "looked_at": None}})
    assert detection_client.status() == (session_id, "starting", None, None, None)
    for wrong in ({"baseline_view": {"taken_at": "not a time"}}, {"registered": {"at": "not a time"}},
                  {"looked_at": "2026-10-22T09:00:05"}):   # a time with no zone is not on first_seen_at's clock
        answers["/status"] = (200, {"run": {**watching, **wrong}})
        with pytest.raises(detection_client.DetectionServiceUnreachable):
            detection_client.status()
    answers["/status"] = (404, {"detail": "not found"})   # something else on its port
    with pytest.raises(detection_client.DetectionServiceUnreachable):
        detection_client.status()

    answers["/runs"] = (200, watching)
    assert detection_client.start_run(session_id, "rtsp://127.0.0.1:8554/lane1") == read
    answers["/runs"] = (409, {"detail": "another Session's Run is active"})
    with pytest.raises(detection_client.RunRefused) as refused:
        detection_client.start_run(session_id, "rtsp://127.0.0.1:8554/lane1")
    assert (refused.value.status, refused.value.detail, refused.value.holder) == (409, "another Session's Run is active", None)
    other = uuid.uuid4()
    answers["/runs"] = (409, {"detail": "another Session's Run is active", "run": {**watching, "session_id": str(other)}})
    with pytest.raises(detection_client.RunRefused) as refused:
        detection_client.start_run(session_id, "rtsp://127.0.0.1:8554/lane1")
    assert refused.value.holder == other

    answers[f"/runs/{session_id}/end"] = (404, {"detail": "no such Run"})
    assert detection_client.end_run(session_id) is None   # already ended, not by this end
    answers[f"/runs/{session_id}/end"] = (200, {"session_id": str(session_id), "state": "ended",
                                                "baseline_view": view.model_dump(mode="json"),
                                                "registered": registered.model_dump(mode="json"),
                                                "looked_at": looked_at})
    assert detection_client.end_run(session_id) == (session_id, "ended", *read[2:])
    for wrong in ((500, {}), (200, {})):
        answers[f"/runs/{session_id}/end"] = wrong
        with pytest.raises(detection_client.DetectionServiceUnreachable):
            detection_client.end_run(session_id)
