"""Stand-ins shared by the camera, recording and detection tests."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.schemas.run import BaselineView
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


def baseline_view(taken_at):
    """A Run's Baseline View as the Detection Service sends it (ADR-0009):
    the artwork at a quarter of its size in a 1920x1080 picture, and two
    Targets, the artwork's own and one to its right."""
    return BaselineView(
        taken_at=taken_at,
        picture={"width": 1920, "height": 1080},
        template_to_picture=[[0.25, 0.0, 600.0], [0.0, 0.25, 300.0], [0.0, 0.0, 1.0]],
        targets=[[[0.0, 0.0], [1405.0, 0.0], [1405.0, 1120.0], [0.0, 1120.0]],
                 [[1600.0, 0.0], [3005.0, 0.0], [3005.0, 1120.0], [1600.0, 1120.0]]],
    )


class FakeDetectionService:
    """The Detection Service's control API (services/detection_service.py),
    holding one Run at a time as the service does: `run`, or None. Every start
    and end made is in `calls`. A start is answered with `start_error` raised,
    a 409 while another Session's Run is active or this one's ending, or else
    as watching, the Run already watching if it is this Session's, or a new
    one whose Baseline View is taken later than any before; `down` makes
    every call go unanswered. `on_status`, `on_start`
    and `on_end` see each call as it happens, a Run being ended reading
    `ending`."""

    def __init__(self, monkeypatch):
        self.calls = []
        self.run = None
        self.start_error = None
        self.down = False
        self.on_status = lambda: None
        self.on_start = self.on_end = lambda session_id: None
        monkeypatch.setattr(detection_service, "start_run", self._start)
        monkeypatch.setattr(detection_service, "end_run", self._end)
        monkeypatch.setattr(detection_service, "status", self._status)

    def _answer(self):
        if self.down:
            raise detection_service.DetectionServiceUnreachable("connection refused")

    def _status(self):
        self.on_status()
        self._answer()
        return self.run

    def _start(self, session_id, stream_url):
        self.calls.append(("start", session_id, stream_url))
        self.on_start(session_id)
        self._answer()
        if self.start_error:
            raise self.start_error
        if self.run and self.run.session_id != session_id:
            raise detection_service.RunRefused(409, "another Session's Run is active")
        if self.run and self.run.state == "ending":
            raise detection_service.RunRefused(409, "the Session's Run is ending")
        if not self.run:   # a repeat start is answered with the Run already watching
            taken_at = NOW + timedelta(seconds=len(self.calls))
            self.run = detection_service.Run(session_id, "watching", baseline_view(taken_at))
        return self.run

    def _end(self, session_id):
        self.calls.append(("end", session_id))
        ending = not self.down and self.run and self.run.session_id == session_id
        if ending:
            self.run = detection_service.Run(session_id, "ending")
        self.on_end(session_id)
        self._answer()
        if ending:
            self.run = None
        return bool(ending)
