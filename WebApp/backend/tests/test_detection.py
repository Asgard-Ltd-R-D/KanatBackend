"""A Session with a camera is watched by a Run of the Detection Service
(ADR-0008), driven through the REST API with the database replaced and the
Detection Service faked at its client module; and that client's reading of
the service's answers."""
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.core.live import hub
from app.main import app
from app.repositories import cameras as cameras_repo
from app.repositories import sessions as sessions_repo
from app.services import camera_sync, detection_service
from app.services import recordings as recording_svc
from tests.fakes import NOW, FakeDetectionService, make_camera


class FakeDB:
    def close(self):
        pass


@pytest.fixture
def db(monkeypatch):
    """The database replaced: its Sessions and cameras by id."""
    state = SimpleNamespace(sessions={}, cameras={})

    def add(db, session):
        session.created_at = NOW
        state.sessions[session.id] = session
        return session

    def by_id(db, session_id):
        return state.sessions.get(session_id)

    monkeypatch.setattr(sessions_repo, "add", add)
    for name in ("get", "get_for_update", "get_with_bullets"):
        monkeypatch.setattr(sessions_repo, name, by_id)
    monkeypatch.setattr(sessions_repo, "save", lambda db: None)
    monkeypatch.setattr(cameras_repo, "get", lambda db, camera_id: state.cameras.get(camera_id))
    # Nothing to tell MediaMTX: the database is fake
    monkeypatch.setattr(camera_sync, "sync_soon", lambda db: None)
    return state


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = FakeDB
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def detection(monkeypatch):
    return FakeDetectionService(monkeypatch)


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
    (detection_service.RunRefused(502, "no Target on the baseline frame"), "stream_failed", "no Target on the baseline frame"),
    (detection_service.RunRefused(409, "another Session's Run is active"), "other_session", "another Session's Run is active"),
    (detection_service.DetectionServiceUnreachable("connection refused"), "service_down", None),
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


def test_completing_still_succeeds_when_the_detection_service_is_down(client, db, detection):
    session_id = client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)}).json()["id"]

    def down(session_id):
        raise detection_service.DetectionServiceUnreachable("connection refused")

    detection.on_end = down

    assert client.patch(f"/sessions/{session_id}", json={"status": "completed"}).json()["status"] == "completed"


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
    detection.start_error = detection_service.RunRefused(409, "the Session's Run is ending")
    detection.on_start = lambda session_id: client.patch(f"/sessions/{session_id}", json={"status": "completed"})

    session_id = client.post("/sessions", json={"name": "Range 1", "camera_id": str(add_camera(db).id)}).json()["id"]

    assert client.get(f"/sessions/{session_id}").json()["detection"]["state"] == "none"


# --- the client ---

def test_the_client_reads_the_detection_services_answers(monkeypatch):
    answers = {}

    def request(method, url, timeout, **kwargs):
        status, body = answers[url.rsplit(":8010", 1)[1]]
        return httpx.Response(status, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr(detection_service.httpx, "request", request)
    session_id = uuid.uuid4()

    answers["/status"] = (200, {"run": None})
    assert detection_service.status() is None
    answers["/status"] = (200, {"run": {"session_id": str(session_id), "state": "watching",
                                        "since": "2026-10-22T09:00:00+00:00", "baseline_marks": 3}})
    assert detection_service.status() == (session_id, "watching")
    answers["/status"] = (404, {"detail": "not found"})   # something else on its port
    with pytest.raises(detection_service.DetectionServiceUnreachable):
        detection_service.status()

    answers["/runs"] = (409, {"detail": "another Session's Run is active"})
    with pytest.raises(detection_service.RunRefused) as refused:
        detection_service.start_run(session_id, "rtsp://127.0.0.1:8554/lane1")
    assert (refused.value.status, refused.value.detail) == (409, "another Session's Run is active")

    answers[f"/runs/{session_id}/end"] = (404, {"detail": "no such Run"})
    detection_service.end_run(session_id)        # already ended
    answers[f"/runs/{session_id}/end"] = (500, {})
    with pytest.raises(detection_service.DetectionServiceUnreachable):
        detection_service.end_run(session_id)
