"""A Session's Runs (ADR-0009): each Run of the Detection Service that watched
it, stored the first time the backend sees it watching, with the camera it
watched and its Baseline View. Driven through the REST API on a real
PostgreSQL, the Detection Service faked at its client module, so skipped
unless TEST_DATABASE_URL is set."""
import uuid
from datetime import datetime

import anyio
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_db
from app.core.live import hub
from app.main import app
from app.services import camera_sync, detection_service
from app.services import detection as detection_svc
from app.services import recordings as recording_svc
from tests.fakes import NOW, FakeDetectionService, baseline_view
from tests.test_schema import URL, alembic_config, db_url  # noqa: F401 (db_url is a fixture)

pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def engine(db_url):
    command.upgrade(alembic_config(), "head")
    engine = create_engine(db_url)
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine, monkeypatch):
    """The app on the test's database, the Detection Service's loop included;
    MediaMTX and the recordings are left alone."""
    local = sessionmaker(bind=engine)
    monkeypatch.setattr(detection_svc, "SessionLocal", local)
    monkeypatch.setattr(camera_sync, "sync_soon", lambda db: None)
    monkeypatch.setattr(recording_svc, "delete_session_video", lambda windows, others: 0)

    def real_db():
        with local() as db:
            yield db

    app.dependency_overrides[get_db] = real_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def detection(monkeypatch):
    return FakeDetectionService(monkeypatch)


@pytest.fixture
def camera(engine):
    camera_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cameras (id, alias, mcast_ip, mcast_port) VALUES (:id, 'lane1', '226.226.226.112', 112)"
        ), {"id": camera_id})
    return camera_id


def start_session(client, camera):
    return uuid.UUID(client.post("/sessions", json={"name": "Range 1", "camera_id": str(camera)}).json()["id"])


def runs_of(client, session_id):
    return client.get(f"/sessions/{session_id}").json()["runs"]


def tick(client):
    """One round of the loop that reconciles the Detection Service's Run, on a
    worker thread of the app's event loop as the loop runs it."""
    client.portal.call(anyio.to_thread.run_sync, detection_svc._reconcile_once)


def taken_at(run):
    return datetime.fromisoformat(run["taken_at"])


def stored_runs(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM runs")).scalar()


def test_a_sessions_detail_returns_its_run_with_its_baseline_view_and_camera(client, detection, camera):
    session_id = start_session(client, camera)

    [run] = runs_of(client, session_id)

    sent = detection.run.baseline_view
    assert run["camera_alias"] == "lane1"
    assert taken_at(run) == sent.taken_at
    assert run["baseline_view"] == sent.model_dump(mode="json")


def test_the_session_list_carries_no_runs(client, detection, camera):
    start_session(client, camera)

    [listed] = client.get("/sessions").json()

    assert "runs" not in listed


def test_a_run_read_again_on_later_ticks_is_stored_once(client, detection, camera, caplog):
    session_id = start_session(client, camera)

    tick(client)
    tick(client)

    assert len(runs_of(client, session_id)) == 1
    assert "not stored" not in caplog.text   # a repeat is no failure to store


def test_a_run_first_seen_through_a_status_read_after_a_restart_is_stored(client, detection, camera):
    # Its start was never answered to this backend: started for it before a
    # restart
    detection.down = True
    session_id = start_session(client, camera)
    detection.down = False
    detection.run = detection_service.Run(session_id, "watching", baseline_view(NOW))
    detection_svc._states.clear()
    calls = list(detection.calls)

    tick(client)

    assert [taken_at(run) for run in runs_of(client, session_id)] == [NOW]
    assert detection.calls == calls   # read, not started again


def test_a_sessions_second_run_is_stored_beside_its_first_in_taken_at_order(client, detection, camera):
    session_id = start_session(client, camera)
    first = detection.run.baseline_view.taken_at
    detection.run = None   # lost: the next tick starts another, from a fresh baseline

    tick(client)

    second = detection.run.baseline_view.taken_at
    assert first < second
    assert [taken_at(run) for run in runs_of(client, session_id)] == [first, second]


def test_a_run_of_a_deleted_session_stores_nothing(client, detection, camera, engine):
    # Deleted while its Run started: the start is answered once it is gone
    detection.on_start = lambda session_id: client.delete(f"/sessions/{session_id}")

    session_id = start_session(client, camera)

    assert client.get(f"/sessions/{session_id}").status_code == 404
    assert detection.run is None   # ended, as any start answered too late is
    assert stored_runs(engine) == 0


def test_deleting_a_session_deletes_its_runs(client, detection, camera, engine):
    session_id = start_session(client, camera)
    assert stored_runs(engine) == 1

    client.delete(f"/sessions/{session_id}")

    assert stored_runs(engine) == 0


@pytest.mark.parametrize("seen_by", ["start", "status read"])
def test_the_run_is_stored_before_the_watching_push_goes_out(client, detection, camera, monkeypatch, seen_by):
    # The frontend refetches the Session on that push, so it brings the Run
    stored_at_push = []
    publish = hub.publish_from_thread

    def publish_watching(session_id, event):
        if getattr(event, "detection", None) == detection_svc.WATCHING:
            stored_at_push.append(len(runs_of(client, session_id)))
        publish(session_id, event)

    monkeypatch.setattr(hub, "publish_from_thread", publish_watching)
    if seen_by == "start":
        start_session(client, camera)
    else:
        detection.down = True
        session_id = start_session(client, camera)
        detection.down = False
        detection.run = detection_service.Run(session_id, "watching", baseline_view(NOW))
        tick(client)

    assert stored_at_push == [1]
