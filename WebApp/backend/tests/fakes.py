"""Stand-ins shared by the camera and recording tests."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import mediamtx

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
