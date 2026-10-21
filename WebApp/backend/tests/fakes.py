"""Stand-ins shared by the camera, recording and detection tests."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import detection_service, mediamtx

NOW = datetime.now(timezone.utc)


def make_camera(alias="cam1", iface=None, enabled=True):
    return SimpleNamespace(
        id=uuid.uuid4(), alias=alias, mcast_ip="226.226.226.112", mcast_port=112,
        iface=iface, enabled=enabled, created_at=NOW,
    )


class FakeMediaMTX:
    """MediaMTX's configured paths, and every change made to them."""

    def __init__(self, monkeypatch, paths=None):
        self.paths = dict(paths or {})
        self.calls = []
        monkeypatch.setattr(mediamtx, "list_path_configs", lambda: dict(self.paths))
        monkeypatch.setattr(mediamtx, "add_path", self._add)
        monkeypatch.setattr(mediamtx, "patch_path", self._patch)
        monkeypatch.setattr(mediamtx, "delete_path", self._delete)

    def _add(self, name, config):
        self.calls.append(("add", name))
        self.paths[name] = dict(config)

    def _patch(self, name, fields):
        self.calls.append(("patch", name, sorted(fields)))
        self.paths[name].update(fields)

    def _delete(self, name):
        self.calls.append(("delete", name))
        del self.paths[name]


class FakeDetectionService:
    """The Detection Service's control API (services/detection_service.py):
    every call made to it, and a start answered with `start_error` raised, or
    else as watching. `on_start` and `on_end` see each call as it happens."""

    def __init__(self, monkeypatch):
        self.calls = []
        self.start_error = None
        self.on_start = self.on_end = lambda session_id: None
        monkeypatch.setattr(detection_service, "start_run", self._start)
        monkeypatch.setattr(detection_service, "end_run", self._end)

    def _start(self, session_id, stream_url):
        self.calls.append(("start", session_id, stream_url))
        self.on_start(session_id)
        if self.start_error:
            raise self.start_error

    def _end(self, session_id):
        self.calls.append(("end", session_id))
        self.on_end(session_id)
