from types import SimpleNamespace

import pytest

from app.config.settings import settings
from app.repositories import cameras as cameras_repo
from app.repositories import runs as runs_repo
from app.repositories import sessions as sessions_repo
from app.services import camera_sync, detection_sync, mediamtx
from app.services import cameras as camera_svc
from app.services import recordings as recording_svc
from tests.fakes import NOW, FakeDB, FakeDetectionService


@pytest.fixture(autouse=True)
def no_camera_sync_loop(monkeypatch):
    """The app's camera sync loop would reach for the real database and MediaMTX."""
    monkeypatch.setattr(settings, "camera_sync_interval_s", 0)


@pytest.fixture(autouse=True)
def fresh_traffic():
    """Each test starts with no remembered byte counters."""
    camera_svc._traffic.clear()


@pytest.fixture(autouse=True)
def no_detection_states():
    """Each test starts with no Session's detection remembered."""
    detection_sync._states.clear()
    detection_sync._watched.clear()
    detection_sync._since.clear()


@pytest.fixture(autouse=True)
def no_parts_in_use():
    """Each test starts with no replay copy being played."""
    recording_svc._in_use.clear()


@pytest.fixture
def db_state(monkeypatch):
    """What sync reads from the database: the cameras and whether to record."""
    state = SimpleNamespace(cameras=[], record=False)
    monkeypatch.setattr(cameras_repo, "list_all", lambda db: state.cameras)
    monkeypatch.setattr(sessions_repo, "recording_session_active", lambda db: state.record)
    return state


@pytest.fixture(autouse=True)
def no_mediamtx_yml_paths(monkeypatch):
    """Tests do not read the repo's mediamtx.yml; one that needs its path names
    sets them."""
    monkeypatch.setattr(mediamtx, "config_paths", lambda: mediamtx.ConfigPaths())


@pytest.fixture
def db(monkeypatch):
    """The database replaced: its Sessions and cameras by id. A Run is
    stored nowhere: tests/test_runs.py stores them on a real database."""
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
    # Sessions are added in the order they start
    monkeypatch.setattr(sessions_repo, "list_active", lambda db: [s for s in state.sessions.values() if s.status == "active"])
    monkeypatch.setattr(cameras_repo, "get", lambda db, camera_id: state.cameras.get(camera_id))
    monkeypatch.setattr(cameras_repo, "list_all", lambda db: list(state.cameras.values()))
    monkeypatch.setattr(detection_sync, "SessionLocal", FakeDB)
    monkeypatch.setattr(sessions_repo, "exists", lambda db, session_id: session_id in state.sessions)
    monkeypatch.setattr(runs_repo, "add_once", lambda db, *run: None)
    monkeypatch.setattr(runs_repo, "get_for_update", lambda db, *run: None)
    # Nothing to tell MediaMTX: the database is fake
    monkeypatch.setattr(camera_sync, "sync_soon", lambda db: None)
    return state


@pytest.fixture
def client(db):
    """The REST API on the `db` fixture's database."""
    from fastapi.testclient import TestClient

    from app.core.deps import get_db
    from app.main import app

    app.dependency_overrides[get_db] = FakeDB
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def detection(monkeypatch):
    """The Detection Service, faked at its client module (tests/fakes.py)."""
    return FakeDetectionService(monkeypatch)
