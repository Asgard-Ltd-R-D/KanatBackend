"""The recordings router (routers/recordings.py) turning a MediaMTX outage into
a 503, so the UI can tell "video service down" from "no such recording"."""
import uuid
from types import SimpleNamespace

from app.services import cameras as camera_svc
from app.services import mediamtx
from app.services import recordings as svc
from app.services import sessions as session_svc


def test_listing_recordings_is_503_when_the_video_service_is_down(client, monkeypatch):
    session_id = uuid.uuid4()
    monkeypatch.setattr(session_svc, "get_session_or_404", lambda sid, db: SimpleNamespace(recording_intervals=[]))
    monkeypatch.setattr(session_svc, "recorded_windows", lambda intervals: [])
    monkeypatch.setattr(camera_svc, "list_cameras", lambda db: [])

    def unreachable(windows, cameras):
        raise mediamtx.MediaMTXUnreachable("playback down")

    monkeypatch.setattr(svc, "session_recordings", unreachable)

    res = client.get(f"/sessions/{session_id}/recordings")

    assert res.status_code == 503
    assert "not reachable" in res.json()["detail"].lower()
