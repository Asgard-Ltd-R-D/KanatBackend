from types import SimpleNamespace

import pytest

from app.config.settings import settings
from app.repositories import cameras as cameras_repo
from app.services import cameras as camera_svc


@pytest.fixture(autouse=True)
def no_camera_sync_loop(monkeypatch):
    """The app's camera sync loop would reach for the real database and MediaMTX."""
    monkeypatch.setattr(settings, "camera_sync_interval_s", 0)


@pytest.fixture(autouse=True)
def fresh_traffic():
    """Each test starts with no remembered byte counters."""
    camera_svc._traffic.clear()


@pytest.fixture
def db_state(monkeypatch):
    """What sync reads from the database: the cameras."""
    state = SimpleNamespace(cameras=[])
    monkeypatch.setattr(cameras_repo, "list_all", lambda db: state.cameras)
    return state
