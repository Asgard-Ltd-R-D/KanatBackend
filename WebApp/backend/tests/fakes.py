"""Stand-ins shared by the camera, recording and detection tests."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.schemas.run import BaselineView, Place
from app.services import detection_client, mediamtx

NOW = datetime.now(timezone.utc)


class FakeDB:
    """A database session that is never used: the repositories it would be
    handed to are replaced (the `db` fixture, tests/conftest.py)."""

    def close(self):
        pass


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
    the artwork at a quarter of its size in a 1920x1080 picture, two
    Targets, the artwork's own and one to its right, and a Baseline Mark on
    each."""
    return BaselineView(
        taken_at=taken_at,
        picture={"width": 1920, "height": 1080},
        template_to_picture=[[0.25, 0.0, 600.0], [0.0, 0.25, 300.0], [0.0, 0.0, 1.0]],
        targets=[[[0.0, 0.0], [1405.0, 0.0], [1405.0, 1120.0], [0.0, 1120.0]],
                 [[1600.0, 0.0], [3005.0, 0.0], [3005.0, 1120.0], [1600.0, 1120.0]]],
        baseline_marks=[[702.5, 560.0], [2310.4, 87.2]],
    )


def place(at, dx=0.0, sx=0.25):
    """Where a Run registered the Board at `at`: where `baseline_view` has
    it, moved `dx` picture px right and scaled `sx` across."""
    return Place(at=at, template_to_picture=[[sx, 0.0, 600.0 + dx], [0.0, 0.25, 300.0], [0.0, 0.0, 1.0]])


class FakeDetectionService:
    """The Detection Service's control API (services/detection_client.py),
    holding a Run per board as the service now does: `runs`, keyed by
    (session_id, camera). Every start and end made is in `calls`. A start is
    answered with `start_error` raised, a 409 while that board's Run is ending,
    or else as watching, the Run already watching for that board, or a new one
    whose Baseline View is taken later than any before, registered and looked at
    only then; `down` makes every call go unanswered. An end, or a stop (`judge`
    false), is answered with the Run's Baseline View and how far it watched.
    `on_status`, `on_start` and `on_end` see each call as it happens, a Run being
    ended reading `ending`; `on_start`/`on_end` are passed (session_id, camera).

    Different boards run concurrently; there is no cross-Session refusal (the
    backend only ever watches the one active Session's cameras)."""

    def __init__(self, monkeypatch):
        self.calls = []
        self.runs: dict[tuple, "detection_client.Run"] = {}
        self.start_error = None
        self.down = False
        self.on_status = lambda: None
        self.on_start = self.on_end = lambda session_id, camera: None
        monkeypatch.setattr(detection_client, "start_run", self._start)
        monkeypatch.setattr(detection_client, "end_run", self._end)
        monkeypatch.setattr(detection_client, "status", self._status)

    def set_run(self, session_id, camera="cam1", state="watching", taken_at=None):
        """Place a Run for a board, as a status read would show it; returns it."""
        taken_at = taken_at or NOW + timedelta(seconds=len(self.runs) + 1)
        run = detection_client.Run(session_id, camera, state, baseline_view(taken_at),
                                   place(taken_at), taken_at)
        self.runs[(session_id, camera)] = run
        return run

    def _answer(self):
        if self.down:
            raise detection_client.DetectionServiceUnreachable("connection refused")

    def _status(self):
        self.on_status()
        self._answer()
        return list(self.runs.values())

    def _start(self, session_id, camera, stream_url):
        self.calls.append(("start", session_id, camera, stream_url))
        self.on_start(session_id, camera)
        self._answer()
        if self.start_error:
            raise self.start_error
        key = (session_id, camera)
        run = self.runs.get(key)
        if run and run.state == "ending":
            raise detection_client.RunRefused(409, "the board's Run is ending", session_id)
        if not run:   # a repeat start is answered with the Run already watching
            taken_at = NOW + timedelta(seconds=len(self.calls))
            run = self.runs[key] = detection_client.Run(session_id, camera, "watching",
                                                        baseline_view(taken_at), place(taken_at), taken_at)
        return run

    def _end(self, session_id, camera, judge=True):
        self.calls.append(("end" if judge else "stop", session_id, camera))
        key = (session_id, camera)
        run = self.runs.get(key) if not self.down else None
        if run:
            self.runs[key] = run._replace(state="ending")
        self.on_end(session_id, camera)
        self._answer()
        if not run:
            return None
        del self.runs[key]
        return run._replace(state="ended")
