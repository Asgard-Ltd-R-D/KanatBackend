from types import SimpleNamespace

import pytest

from app.config.settings import settings
from app.repositories import cameras as cameras_repo
from app.repositories import sessions as sessions_repo
from app.services import cameras as camera_svc
from app.services import detection, mediamtx
from app.services import recordings as recording_svc


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
    detection._states.clear()
    detection._watched.clear()


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
