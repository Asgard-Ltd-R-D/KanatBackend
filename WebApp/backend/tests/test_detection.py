"""A Session spans every enabled camera, one board each, and a Run of the
Detection Service watches each board (ADR-0008), on that camera's Stream. Driven
through the REST API with the database replaced and the Detection Service faked
at its client module; and that client's reading of the service's answers. Each
board is keyed by (session_id, camera alias)."""
import json
import uuid
from contextlib import contextmanager
from datetime import datetime

import anyio
import httpx
import pytest
from sqlalchemy.exc import PendingRollbackError

from app.core.live import hub
from app.repositories import bullets as bullets_repo
from app.repositories import runs as runs_repo
from app.repositories import sessions as sessions_repo
from app.services import detection_client, detection_sync
from app.services import sessions as sessions_svc
from tests.fakes import NOW, FakeDB, baseline_view, make_camera, place

CAM = "lane1"
STREAM = "rtsp://127.0.0.1:8554/lane1"


def add_camera(db, alias=CAM, enabled=True):
    camera = make_camera(alias, enabled=enabled)
    db.cameras[camera.id] = camera
    return camera


@pytest.fixture
def streams(detection):
    """Each Session's live stream by its id, subscribed when a board's Run is
    asked for: as the frontend listens once the create call has answered."""
    subscribed = {}
    detection.on_start = lambda session_id, camera: subscribed.setdefault(session_id, hub.subscribe(session_id))
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


def start_session(client, camera=None, **body):
    """Create a Session. `camera` is already in the fake database (add_camera),
    so the Session spans it; it is accepted here only to keep call sites short."""
    return uuid.UUID(client.post("/sessions", json={"name": "Range 1", **body}).json()["id"])


def board(resp_json, camera=CAM):
    """One board's detection out of a Session response's `detections`; a board
    with no state reads `none`, as the frontend shows it."""
    for b in resp_json["detections"]:
        if b["camera_alias"] == camera:
            return b["detection"]
    return {"state": "none", "reason": None, "detail": None}


def detection_of(client, session_id, camera=CAM):
    return board(client.get(f"/sessions/{session_id}").json(), camera)


def run_of(detection, session_id, camera=CAM):
    return detection.runs.get((session_id, camera))


def tick(client):
    """One round of the loop that reconciles the Detection Service's Runs, on a
    worker thread of the app's event loop as the loop runs it."""
    client.portal.call(anyio.to_thread.run_sync, detection_sync.reconcile, FakeDB())


def not_watching(reason):
    return {"state": "not_watching", "reason": reason, "detail": None}


WATCHING = {"state": "watching", "reason": None, "detail": None}


# --- starting ---

def test_a_session_asks_for_a_run_on_each_enabled_cameras_stream(client, db, detection):
    add_camera(db)

    res = client.post("/sessions", json={"name": "Range 1"})

    assert res.status_code == 201
    session_id = uuid.UUID(res.json()["id"])
    assert detection.calls == [("start", session_id, CAM, STREAM)]


def test_a_session_spans_every_enabled_camera_one_board_each(client, db, detection):
    add_camera(db, "lane1")
    add_camera(db, "lane2")
    add_camera(db, "lane3", enabled=False)   # disabled: no board

    session_id = uuid.UUID(client.post("/sessions", json={"name": "Range 1"}).json()["id"])

    assert sorted(c[2] for c in detection.calls) == ["lane1", "lane2"]
    boards = {b["camera_alias"]: b["detection"]["state"]
              for b in client.get(f"/sessions/{session_id}").json()["detections"]}
    assert boards == {"lane1": "watching", "lane2": "watching"}


def test_a_session_with_no_enabled_camera_asks_for_nothing(client, db, detection):
    add_camera(db, enabled=False)

    res = client.post("/sessions", json={"name": "Range 1"})

    assert res.json()["detections"] == []
    assert detection.calls == []


def test_unknown_session_fields_are_refused(client, db, detection):
    # SessionUpdate forbids extra fields: a Session has no camera to change
    session_id = client.post("/sessions", json={"name": "Range 1"}).json()["id"]

    res = client.patch(f"/sessions/{session_id}", json={"camera_id": str(uuid.uuid4())})

    assert res.status_code == 422


def test_the_board_is_starting_then_watching_and_says_so_live(client, db, detection, streams):
    add_camera(db)

    res = client.post("/sessions", json={"name": "Range 1"})
    session_id = uuid.UUID(res.json()["id"])

    # Answered at once, before the Run is watching
    assert board(res.json())["state"] == "starting"
    assert events(streams[session_id]) == [
        {"type": "detection_updated", "camera_alias": CAM,
         "detection": {"state": "watching", "reason": None, "detail": None}},
    ]
    assert detection_of(client, session_id)["state"] == "watching"


@pytest.mark.parametrize("error, reason, detail", [
    (detection_client.RunRefused(502, "no Target on the baseline frame"), "stream_failed", "no Target on the baseline frame"),
    (detection_client.RunRefused(409, "another Session's Run is active"), "other_session", "another Session's Run is active"),
    (detection_client.DetectionServiceUnreachable("connection refused"), "service_down", None),
])
def test_a_start_that_fails_reads_not_watching_with_its_reason(client, db, detection, streams, error, reason, detail):
    add_camera(db)
    detection.start_error = error

    session_id = uuid.UUID(client.post("/sessions", json={"name": "Range 1"}).json()["id"])

    expected = {"state": "not_watching", "reason": reason, "detail": detail}
    assert events(streams[session_id]) == [{"type": "detection_updated", "camera_alias": CAM, "detection": expected}]
    assert detection_of(client, session_id) == expected


# --- ending ---

def test_completing_a_session_ends_its_run_before_it_reads_completed(client, db, detection):
    session_id = start_session(client, add_camera(db))
    status_at_end = []
    detection.on_end = lambda sid, camera: status_at_end.append(db.sessions[sid].status)
    stream = hub.subscribe(session_id)
    try:
        res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})
        seen = [(e["type"], e.get("detection", {}).get("state") or e.get("status")) for e in events(stream)]
    finally:
        hub.unsubscribe(session_id, stream)

    assert status_at_end == ["active"]       # its last posts are still stored
    assert res.json()["status"] == "completed"
    assert board(res.json())["state"] == "none"
    assert seen == [
        ("detection_updated", "ending"),
        ("detection_updated", "none"),
        ("session_updated", "completed"),
    ]


def test_completing_a_session_ends_every_board_together(client, db, detection):
    """Each enabled camera's Run is ended, in parallel (detection_sync ends the
    boards at once), before the Session reads completed."""
    add_camera(db, "lane1")
    add_camera(db, "lane2")
    session_id = uuid.UUID(client.post("/sessions", json={"name": "Range 1"}).json()["id"])

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert res.json()["status"] == "completed"
    assert {c for c in detection.calls if c[0] == "end"} == {
        ("end", session_id, "lane1"), ("end", session_id, "lane2"),
    }


def test_board_ends_do_not_deadlock_when_the_request_workers_are_full():
    """ending() runs in a sync request, which holds one default worker token and
    blocks in _in_parallel while its board ends run. If those ends drew from the
    default pool too, enough concurrent completions would hold every token while
    waiting for ends that can never get one. The ends run on their own pool, so
    saturating the default one does not wedge them: with every default token held
    by a waiting parent, the fan-out still finishes."""
    async def main():
        default = anyio.to_thread.current_default_thread_limiter()
        default.total_tokens = 3   # tiny: three parents hold them all, none to spare

        def parent(_: str) -> None:   # a sync request body fanning its ends out
            detection_sync._in_parallel(lambda camera: None, ["a", "b"])

        with anyio.fail_after(10):    # a deadlock would hang here instead
            async with anyio.create_task_group() as task_group:
                for i in range(3):
                    task_group.start_soon(anyio.to_thread.run_sync, parent, str(i))

    anyio.run(main)


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
    monkeypatch.setattr(bullets_repo, "count_active", lambda db, session_id, camera_alias: len(stored))
    monkeypatch.setattr(bullets_repo, "add", add)
    session_id = start_session(client, add_camera(db))
    posted = []
    detection.on_end = lambda sid, camera: posted.append(client.post(f"/sessions/{sid}/bullets", json={
        "version": "v2", "camera": camera, "first_seen_at": NOW.isoformat(), "position": {"x": 100, "y": 200}}).status_code)

    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert posted == [201]
    assert [(b.session_id, b.camera_alias) for b in stored] == [(session_id, CAM)]


END_UNCONFIRMED = {"state": "end_unconfirmed", "reason": None, "detail": None}


def test_completing_still_succeeds_when_the_detection_service_is_down(client, db, detection):
    # Or does not answer in time: the client raises the same for both
    session_id = start_session(client, add_camera(db))

    def down(session_id, camera):
        raise detection_client.DetectionServiceUnreachable("connection refused")

    detection.on_end = down

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    tick(client)

    assert res.json()["status"] == "completed"
    # The page says so, and keeps saying it: its last Bullet Holes may be missing
    assert board(res.json()) == END_UNCONFIRMED
    assert detection_of(client, session_id) == END_UNCONFIRMED


def test_a_watched_board_whose_run_is_already_gone_reads_end_unconfirmed(client, db, detection):
    # Lost since the last tick, which still read watching: the 404 for no such
    # Run does not say what it saw last was posted
    session_id = start_session(client, add_camera(db))
    detection.runs.clear()

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert board(res.json()) == END_UNCONFIRMED


def test_a_watched_board_read_not_watching_since_reads_end_unconfirmed(client, db, detection):
    # A tick while the Detection Service was down read it service_down: its
    # Run may still hold its last shots
    session_id = start_session(client, add_camera(db))
    detection.down = True
    tick(client)

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert board(res.json()) == END_UNCONFIRMED


def test_a_board_whose_run_ended_while_the_session_was_active_reads_none(client, db, detection):
    # Its camera disabled: the Run's end was confirmed while the Session still
    # stored what it posted
    camera = add_camera(db)
    session_id = start_session(client, camera)
    camera.enabled = False
    tick(client)

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert board(res.json())["state"] == "none"


def test_a_run_another_end_confirmed_meanwhile_leaves_the_end_confirmed(client, db, detection):
    # A tick, its camera disabled, ended the Run while the Session was still
    # active, just before this end reached the Detection Service: no such Run
    session_id = start_session(client, add_camera(db))
    run = detection.runs.pop((session_id, CAM))   # lost, as a tick's end took it

    def ended_by_a_tick(sid, camera):
        detection.on_end = lambda sid, camera: None
        detection.runs[(sid, camera)] = run
        detection_sync._end_run(sid, camera)

    detection.on_end = ended_by_a_tick

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert board(res.json())["state"] == "none"


def test_a_board_no_run_watched_reads_none_however_its_end_went(client, db, detection):
    # Its Run never started: nothing of its own was in flight
    detection.start_error = detection_client.RunRefused(502, "no Target on the baseline frame")
    waiting = start_session(client, add_camera(db))
    detection.down = True

    res = client.patch(f"/sessions/{waiting}", json={"status": "completed"})

    assert board(res.json())["state"] == "none"


def test_completing_ends_the_run_of_a_session_whose_camera_was_deleted(client, db, detection):
    camera = add_camera(db)
    session_id = start_session(client, camera)
    del db.cameras[camera.id]   # the camera deleted

    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    # The board was watching, so the end still ends its Run
    assert detection.calls[-1] == ("end", session_id, CAM)


def test_deleting_an_active_session_ends_its_run(client, db, detection, monkeypatch):
    monkeypatch.setattr(sessions_repo, "delete", lambda _, session: db.sessions.pop(session.id))
    session_id = start_session(client, add_camera(db))

    assert client.delete(f"/sessions/{session_id}").status_code == 204
    assert detection.calls[-1] == ("end", session_id, CAM)
    assert session_id not in db.sessions


def test_a_run_that_starts_after_its_session_ended_is_ended(client, db, detection):
    # The end reached the Detection Service first and found no Run (404)
    add_camera(db)
    detection.on_start = lambda session_id, camera: client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    session_id = uuid.UUID(client.post("/sessions", json={"name": "Range 1"}).json()["id"])

    assert [call[0] for call in detection.calls] == ["start", "end", "end"]
    assert detection_of(client, session_id)["state"] == "none"


def test_a_start_answered_after_the_session_ended_changes_nothing(client, db, detection):
    # The operator ends the Session while its Run is still starting: the
    # service then refuses the start, which must not mark a completed Session
    # as not watching
    add_camera(db)
    detection.start_error = detection_client.RunRefused(409, "the Session's Run is ending")
    detection.on_start = lambda session_id, camera: client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    session_id = client.post("/sessions", json={"name": "Range 1"}).json()["id"]

    assert detection_of(client, session_id)["state"] == "none"


# --- reconciling every few seconds ---

def test_a_detection_service_back_up_with_no_run_gets_it_from_the_next_tick(client, db, detection):
    session_id = start_session(client, add_camera(db))
    with listening(session_id) as stream:
        detection.down = True   # the Detection Service restarts
        detection.runs.clear()
        tick(client)
        while_down = detection_of(client, session_id)
        detection.down = False
        tick(client)
        seen = [e["detection"] for e in events(stream)]

    assert while_down == not_watching("service_down")
    assert detection.calls[-1] == ("start", session_id, CAM, STREAM)
    assert seen == [not_watching("service_down"), WATCHING]


def test_a_run_lost_while_the_service_is_up_reads_not_watching_until_it_is_back(client, db, detection):
    session_id = start_session(client, add_camera(db))
    with listening(session_id) as stream:
        detection.runs.clear()   # its Stream failed, or the service restarted between two ticks
        tick(client)
        seen = [e["detection"] for e in events(stream)]

    assert detection.calls[-1] == ("start", session_id, CAM, STREAM)
    assert seen == [not_watching(None), WATCHING]


def test_the_run_of_a_session_completed_while_the_service_was_down_is_ended(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection.down = True
    client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    detection.down = False

    tick(client)

    assert detection.calls[-1] == ("end", session_id, CAM)
    assert run_of(detection, session_id) is None
    # Ended after the Session completed: what it posted on the way out was refused
    assert detection_of(client, session_id) == END_UNCONFIRMED


def test_the_run_of_a_deleted_session_is_ended(client, db, detection):
    deleted = uuid.uuid4()
    detection.set_run(deleted, CAM)

    tick(client)

    assert detection.calls == [("end", deleted, CAM)]


@pytest.mark.parametrize("change", ["disabled", "deleted"])
def test_a_camera_disabled_or_deleted_mid_session_ends_its_run(client, db, detection, change):
    camera = add_camera(db)
    session_id = start_session(client, camera)
    if change == "disabled":
        camera.enabled = False
    else:
        del db.cameras[camera.id]

    tick(client)
    calls = list(detection.calls)
    tick(client)

    assert calls[-1] == ("end", session_id, CAM)
    assert detection.calls == calls   # and is not started again
    session = client.get(f"/sessions/{session_id}").json()
    assert (session["status"], board(session)) == ("active", not_watching("camera_disabled"))


@pytest.mark.parametrize("confirmed", [True, False])
def test_a_reopened_session_gets_a_new_run(client, db, detection, confirmed):
    session_id = start_session(client, add_camera(db))
    detection.down = not confirmed   # its end is not confirmed, and its Run left
    client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    detection.down = False
    tick(client)   # ends the Run of a Session no longer active
    client.patch(f"/sessions/{session_id}", json={"status": "active"})

    tick(client)

    assert detection.calls[-1] == ("start", session_id, CAM, STREAM)
    assert detection_of(client, session_id) == WATCHING


def test_after_a_backend_restart_a_watched_session_reads_watching_by_the_next_tick(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection_sync._states.clear()   # the backend restarted; its Run did not
    calls = list(detection.calls)

    tick(client)

    assert detection_of(client, session_id) == WATCHING
    assert detection.calls == calls


def test_completing_after_a_restart_ends_a_run_the_service_still_watches(client, db, detection):
    """The backend restarted, losing its cached boards, but the Detection
    Service still watches the Session. Completing it must discover that Run and
    end it before the Session reads completed, or the Run's last Bullet Holes
    would be posted after completion and silently lost."""
    session_id = start_session(client, add_camera(db))
    detection_sync._states.clear()   # the backend restarted; its Run did not
    status_at_end = []
    detection.on_end = lambda sid, camera: status_at_end.append(db.sessions[sid].status)

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert res.json()["status"] == "completed"
    assert detection.calls[-1] == ("end", session_id, CAM)   # discovered from the service and ended
    assert status_at_end == ["active"]                        # ended before the Session read completed


def test_completing_after_a_restart_recovers_boards_from_stored_runs_when_discovery_fails(client, db, detection, monkeypatch):
    """When the status() discovery itself is unreachable after a restart, the
    Session's boards are recovered from its stored Runs, so a Run the service may
    still hold is ended (here it warns, the service being down) rather than left
    to post into the completed Session."""
    session_id = start_session(client, add_camera(db))
    detection_sync._states.clear()   # the backend restarted; its Run did not
    detection.down = True            # both the status() discovery and the end are unreachable
    monkeypatch.setattr(runs_repo, "cameras_of", lambda d, sid: [CAM] if sid == session_id else [])

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert res.json()["status"] == "completed"
    assert detection.calls[-1] == ("end", session_id, CAM)   # recovered from stored Runs and ended
    assert board(res.json())["state"] == "end_unconfirmed"   # the end went unconfirmed: last shots may be missing


def test_completing_does_not_rewarn_a_removed_cameras_ended_board(client, db, detection, monkeypatch):
    """A camera removed mid-Session had its Run ended (confirmed) when it was
    disabled; its stored Run row remains, and after a restart _states is empty.
    Completing with the service reachable must not re-open that board as
    end_unconfirmed: the camera is gone, so its end was the clean removal."""
    camera = add_camera(db)
    session_id = start_session(client, camera)   # lane1 watching
    camera.enabled = False                       # its camera was removed mid-Session
    detection.runs.clear()                       # its Run was ended and cleared
    detection_sync._states.clear()               # the backend restarted
    detection_sync._watched.clear()
    monkeypatch.setattr(runs_repo, "cameras_of", lambda d, sid: [CAM])

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert ("end", session_id, CAM) not in detection.calls           # not re-ended
    assert board(res.json(), CAM)["state"] == "none"                 # not a warned board
    assert detection_sync.state_of(session_id, CAM).state == "none"  # not end_unconfirmed


def test_completing_after_a_restart_warns_an_enabled_boards_lost_run(client, db, detection, monkeypatch):
    """A board still enabled whose Run vanished (a Stream failure or a Detection
    Service crash drops it) is not in a reachable status either, but absence is
    not a confirmed end: after a restart it is recovered from its stored Run and
    warned end_unconfirmed, so missing last shots are not hidden."""
    session_id = start_session(client, add_camera(db))   # lane1 enabled, watching
    detection.runs.clear()                               # its Run vanished (not a clean end)
    detection_sync._states.clear()                       # the backend restarted
    detection_sync._watched.clear()
    monkeypatch.setattr(runs_repo, "cameras_of", lambda d, sid: [CAM])

    res = client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert ("end", session_id, CAM) in detection.calls       # recovered and its end attempted
    assert board(res.json(), CAM)["state"] == "end_unconfirmed"   # its last shots may be missing


def test_a_tick_during_completion_starts_no_run_for_a_newly_enabled_camera(client, db, detection):
    """A camera enabled in the completion window must not get a Run from a
    concurrent tick: such a Run would outlive the completed Session and its last
    Bullet Holes would be rejected. The Session's end guards all its boards."""
    session_id = start_session(client, add_camera(db))                        # lane1, watching
    add_camera(db, alias="lane2")                                             # enabled, never started
    detection.on_end = lambda sid, camera: detection_sync.reconcile(FakeDB())  # a tick mid-completion

    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    # lane2 was never started; only lane1's Run was started and ended
    assert [c for c in detection.calls if c[0] == "start"] == [("start", session_id, CAM, STREAM)]


def test_a_session_started_during_a_tick_keeps_its_run(client, db, detection):
    # Its Run is in the Detection Service's status, so its Session is read
    camera, started = add_camera(db), []

    def start_one():
        if not started:
            started.append(start_session(client, camera))

    detection.on_status = start_one

    tick(client)

    assert run_of(detection, started[0]).state == "watching"
    assert [call[0] for call in detection.calls] == ["start"]


def test_a_second_start_for_a_watched_board_leaves_its_run(client, db, detection):
    # The create's own start and a tick's can both ask for the Run, and the
    # Detection Service answers both with the one Run
    session_id = start_session(client, add_camera(db))

    client.portal.call(anyio.to_thread.run_sync, detection_sync.watch, session_id, CAM)

    assert run_of(detection, session_id).state == "watching"
    assert detection_of(client, session_id) == WATCHING


def test_a_tick_while_a_session_ends_leaves_it_to_its_end(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection.on_end = lambda sid, camera: detection_sync.reconcile(FakeDB())

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

    assert detection_sync.state_of(session_id, CAM).state == "none"
    tick(client)
    assert detection.calls[-1] == ("start", session_id, CAM, STREAM)
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
    key = (session_id, CAM)
    detection.runs[key] = detection.runs[key]._replace(state="starting")   # a lost Run's, still ending
    detection.start_error = detection_client.RunRefused(409, "the Session's Run is ending", session_id)
    detection_sync._states[key] = detection_sync.RUN_LOST

    client.portal.call(anyio.to_thread.run_sync, lambda: detection_sync.watch(session_id, CAM, ("not_watching",)))

    assert detection_of(client, session_id) == {"state": "not_watching", "reason": None,
                                                "detail": "the Session's Run is ending"}


def test_a_start_lost_to_an_error_is_let_go_by_a_tick(client, db, detection):
    session_id = start_session(client, add_camera(db))
    key = (session_id, CAM)
    detection.runs.clear()
    client.portal.call(anyio.to_thread.run_sync, detection_sync._set, key, detection_sync.Detection(state="starting"))
    calls = list(detection.calls)
    tick(client)
    assert detection.calls == calls   # still under way, as far as the tick knows

    detection_sync._since[key] -= detection_sync.STUCK_S + 1
    tick(client)   # lets it go
    tick(client)   # and watches it again

    assert detection.calls[-1] == ("start", session_id, CAM, STREAM)
    assert detection_of(client, session_id) == WATCHING


def test_a_slow_end_is_never_let_go_while_its_completion_is_under_way(client, db, detection, monkeypatch):
    # The completion's commit hangs past STUCK_S: a tick meanwhile starts no
    # Run for the Session being completed
    session_id = start_session(client, add_camera(db))
    key = (session_id, CAM)
    update = sessions_svc.update_session

    def slow(*args):
        detection_sync._since[key] -= detection_sync.STUCK_S + 1
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
    detection.runs.clear()
    update = sessions_svc.update_session

    def fail_after(*args):
        update(*args)
        raise RuntimeError("the database went away")

    monkeypatch.setattr(sessions_svc, "update_session", fail_after)
    with pytest.raises(RuntimeError):
        client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert detection_of(client, session_id) == END_UNCONFIRMED


def test_a_completion_that_fails_mid_flush_still_lets_go_of_ending(client, db, detection, monkeypatch):
    # A flush that fails leaves the Session expired in a transaction to roll
    # back: reading its id then raises, so the end must not need it
    session_id = start_session(client, add_camera(db))
    found, failed = sessions_svc.get_session_or_404, []

    class Expired:
        """The Session as the failed flush leaves it."""

        def __init__(self, session):
            self.session = session

        def __getattr__(self, name):
            if failed:
                raise PendingRollbackError("This Session's transaction has been rolled back", None, None)
            return getattr(self.session, name)

    def fail_mid_flush(*args):
        failed.append(True)
        raise RuntimeError("the connection dropped")

    monkeypatch.setattr(sessions_svc, "get_session_or_404", lambda *args: Expired(found(*args)))
    monkeypatch.setattr(sessions_svc, "update_session", fail_mid_flush)
    with pytest.raises(RuntimeError):
        client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert detection_sync.state_of(session_id, CAM).state == "none"


def test_a_run_already_ending_is_left_to_its_end(client, db, detection):
    # Its end blocks for up to END_TIMEOUT_S: a tick does not wait on it again
    session_id = start_session(client, add_camera(db))
    key = (session_id, CAM)
    run = detection.runs[key]
    client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    detection.runs[key] = run._replace(state="ending")   # its end not answered yet
    calls = list(detection.calls)

    tick(client)

    assert detection.calls == calls


def test_a_session_no_longer_active_reads_none_by_the_next_tick(client, db, detection):
    session_id = start_session(client, add_camera(db))
    client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    # As a start that raced its end leaves it
    detection_sync._states[(session_id, CAM)] = detection_sync.RUN_LOST

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


# --- retaking the baseline ---

def test_retaking_the_baseline_ends_the_run_and_watches_from_a_new_one(client, db, detection):
    session_id = start_session(client, add_camera(db))
    key = (session_id, CAM)
    first = detection.runs[key]
    state_at_start = []
    detection.on_start = lambda sid, camera: state_at_start.append(detection_sync.state_of(sid, camera).state)

    with listening(session_id) as stream:
        res = client.post(f"/sessions/{session_id}/baseline/{CAM}")
        pushed = events(stream)

    assert res.status_code == 200
    assert board(res.json())["state"] == "starting"
    # Stopped: what the old Run has open is the re-hang, not a shot
    assert detection.calls[-2:] == [("stop", session_id, CAM), ("start", session_id, CAM, STREAM)]
    assert detection.runs[key].baseline_view.taken_at > first.baseline_view.taken_at
    # "Detection ready" only once the new Run's baseline is built
    assert state_at_start == ["starting"]
    assert [e["detection"]["state"] for e in pushed] == ["starting", "watching"]
    session = client.get(f"/sessions/{session_id}").json()
    assert (session["status"], board(session)) == ("active", WATCHING)


def test_a_tick_during_a_retake_leaves_it_to_finish(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection.on_end = lambda sid, camera: tick(client)

    client.post(f"/sessions/{session_id}/baseline/{CAM}")

    assert [c[0] for c in detection.calls] == ["start", "stop", "start"]
    assert detection_of(client, session_id) == WATCHING


def test_a_retake_while_detection_is_starting_is_refused(client, db, detection):
    session_id = start_session(client, add_camera(db))
    detection_sync._states[(session_id, CAM)] = detection_sync.Detection(state="starting")   # a start under way
    calls = list(detection.calls)

    res = client.post(f"/sessions/{session_id}/baseline/{CAM}")

    assert res.status_code == 409
    assert detection.calls == calls


def test_a_retake_whose_stop_is_unanswered_starts_no_run_until_the_old_one_is_stopped(client, db, detection):
    """A start now would be answered with the old Run, the old sheet's
    baseline: the tick that finds it still there stops it, not adopts it."""
    session_id = start_session(client, add_camera(db))
    key = (session_id, CAM)
    old = detection.runs[key]
    detection.down = True

    client.post(f"/sessions/{session_id}/baseline/{CAM}")

    assert detection.calls[-1] == ("stop", session_id, CAM) and detection.runs[key] == old
    assert detection_of(client, session_id)["reason"] == "service_down"
    detection.down = False
    tick(client)
    assert detection.calls[-2:] == [("stop", session_id, CAM), ("start", session_id, CAM, STREAM)]
    assert detection.runs[key].baseline_view.taken_at > old.baseline_view.taken_at
    assert detection_of(client, session_id) == WATCHING


def test_a_retake_whose_stop_ended_the_run_but_lost_its_answer_keeps_the_new_run(client, db, detection):
    """The service stopped the old Run, but its answer timed out: the tick
    that finds no Run starts one, and no later tick stops it as the old."""
    session_id = start_session(client, add_camera(db))
    detection.down = True
    client.post(f"/sessions/{session_id}/baseline/{CAM}")
    detection.down = False
    detection.runs.clear()

    tick(client)
    new = run_of(detection, session_id)
    tick(client)

    assert detection.calls[-1] == ("start", session_id, CAM, STREAM)
    assert run_of(detection, session_id) == new and detection_of(client, session_id) == WATCHING


def test_a_retake_whose_stop_is_unanswered_stops_a_run_of_it_still_starting(client, db, detection):
    """One left starting, by a backend that restarted, may build its baseline
    from before the re-hang: stopped, not cleared as gone and adopted."""
    session_id = start_session(client, add_camera(db))
    key = (session_id, CAM)
    detection.down = True
    client.post(f"/sessions/{session_id}/baseline/{CAM}")
    old = detection.runs[key]
    detection.down = False
    detection.runs[key] = old._replace(state="starting")

    tick(client)

    # The retake's unanswered stop, then the tick's
    assert detection.calls[-3:] == [("stop", session_id, CAM), ("stop", session_id, CAM),
                                    ("start", session_id, CAM, STREAM)]
    assert detection.runs[key].baseline_view.taken_at > old.baseline_view.taken_at
    assert detection_of(client, session_id) == WATCHING


def test_completing_a_session_before_its_retake_runs_stops_its_run(client, db, detection):
    """Completed between the retake's answer and its background stop: the
    end stops the Run, its open Candidates the re-hang's, not judged."""
    session_id = start_session(client, add_camera(db))
    # The request, its task not yet run
    assert client.portal.call(anyio.to_thread.run_sync, detection_sync.retaking_baseline, session_id, CAM)

    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert detection.calls[-1] == ("stop", session_id, CAM) and run_of(detection, session_id) is None


def test_completing_a_session_whose_retake_stop_is_unanswered_stops_its_run(client, db, detection):
    """Its Run's open Candidates are the re-hang's, so not judged at the end."""
    session_id = start_session(client, add_camera(db))
    detection.down = True
    client.post(f"/sessions/{session_id}/baseline/{CAM}")
    detection.down = False

    client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    assert detection.calls[-1] == ("stop", session_id, CAM) and run_of(detection, session_id) is None


@pytest.mark.parametrize("case", ["completed", "unknown_camera", "camera_disabled"])
def test_only_an_active_session_with_an_enabled_camera_retakes_its_baseline(client, db, detection, case):
    camera = add_camera(db)
    session_id = start_session(client, camera)
    target = CAM
    if case == "completed":
        client.patch(f"/sessions/{session_id}", json={"status": "completed"})
    if case == "camera_disabled":
        camera.enabled = False
    if case == "unknown_camera":
        target = "lane404"
    calls = list(detection.calls)

    res = client.post(f"/sessions/{session_id}/baseline/{target}")

    assert res.status_code == 409
    assert detection.calls == calls


def test_retaking_the_baseline_of_an_unknown_session_is_404(client, db, detection):
    assert client.post(f"/sessions/{uuid.uuid4()}/baseline/{CAM}").status_code == 404


# --- the client ---

def test_the_client_reads_the_detection_services_answers(monkeypatch):
    answers = {}

    def request(method, url, timeout, **kwargs):
        status, body = answers[url.rsplit(":8010", 1)[1]]
        return httpx.Response(status, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr(detection_client.httpx, "request", request)
    session_id = uuid.uuid4()

    answers["/status"] = (200, {"runs": []})
    assert detection_client.status() == []
    view, registered = baseline_view(NOW), place(NOW, dx=3.0)
    looked_at = "2026-10-22T09:00:05.560+00:00"
    watching = {"session_id": str(session_id), "camera": CAM, "state": "watching",
                "since": "2026-10-22T09:00:00+00:00",
                "baseline_marks": 3, "baseline_view": view.model_dump(mode="json"),
                "registered": registered.model_dump(mode="json"), "looked_at": looked_at}
    read = detection_client.Run(session_id, CAM, "watching", view, registered, datetime.fromisoformat(looked_at))
    answers["/status"] = (200, {"runs": [watching]})
    assert detection_client.status() == [read]
    answers["/status"] = (200, {"runs": [{**watching, "state": "starting", "baseline_view": None,
                                          "registered": None, "looked_at": None}]})
    assert detection_client.status() == [detection_client.Run(session_id, CAM, "starting", None, None, None)]
    for wrong in ({"baseline_view": {"taken_at": "not a time"}}, {"registered": {"at": "not a time"}},
                  {"looked_at": "2026-10-22T09:00:05"}):   # a time with no zone is not on first_seen_at's clock
        answers["/status"] = (200, {"runs": [{**watching, **wrong}]})
        with pytest.raises(detection_client.DetectionServiceUnreachable):
            detection_client.status()
    answers["/status"] = (404, {"detail": "not found"})   # something else on its port
    with pytest.raises(detection_client.DetectionServiceUnreachable):
        detection_client.status()

    answers["/runs"] = (200, watching)
    assert detection_client.start_run(session_id, CAM, STREAM) == read
    answers["/runs"] = (409, {"detail": "another Session's Run is active"})
    with pytest.raises(detection_client.RunRefused) as refused:
        detection_client.start_run(session_id, CAM, STREAM)
    assert (refused.value.status, refused.value.detail, refused.value.holder) == (409, "another Session's Run is active", None)
    other = uuid.uuid4()
    answers["/runs"] = (409, {"detail": "another Session's Run is active", "run": {**watching, "session_id": str(other)}})
    with pytest.raises(detection_client.RunRefused) as refused:
        detection_client.start_run(session_id, CAM, STREAM)
    assert refused.value.holder == other

    answers[f"/runs/{session_id}/{CAM}/end"] = (404, {"detail": "no such Run"})
    assert detection_client.end_run(session_id, CAM) is None   # already ended, not by this end
    ended = {"session_id": str(session_id), "camera": CAM, "state": "ended",
             "baseline_view": view.model_dump(mode="json"),
             "registered": registered.model_dump(mode="json"), "looked_at": looked_at}
    answers[f"/runs/{session_id}/{CAM}/end"] = (200, ended)
    assert detection_client.end_run(session_id, CAM) == detection_client.Run(
        session_id, CAM, "ended", view, registered, datetime.fromisoformat(looked_at))
    answers[f"/runs/{session_id}/{CAM}/stop"] = answers[f"/runs/{session_id}/{CAM}/end"]
    assert detection_client.end_run(session_id, CAM, judge=False) == detection_client.Run(
        session_id, CAM, "ended", view, registered, datetime.fromisoformat(looked_at))
    for wrong in ((500, {}), (200, {})):
        answers[f"/runs/{session_id}/{CAM}/end"] = wrong
        with pytest.raises(detection_client.DetectionServiceUnreachable):
            detection_client.end_run(session_id, CAM)
