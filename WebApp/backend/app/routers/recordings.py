import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pydantic import AwareDatetime
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.core.ranges import file_response
from app.schemas.camera import Alias
from app.schemas.recording import CameraRecording
from app.services import cameras as camera_svc
from app.services import mediamtx
from app.services import recordings as svc
from app.services import sessions as session_svc

router = APIRouter(prefix="/sessions/{session_id}/recordings", tags=["recordings"])

# The video comes from MediaMTX's playback server, which listens on this PC
# only, so the frontend talks to the backend alone


@router.get("", response_model=list[CameraRecording])
def list_recordings(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    session = session_svc.get_session_or_404(session_id, db)
    windows = session_svc.recorded_windows(session.recording_intervals)
    try:
        return svc.session_recordings(windows, camera_svc.list_cameras(db))
    except mediamtx.MediaMTXUnreachable:
        raise HTTPException(status_code=503, detail="The video service is not reachable")


@router.get("/{alias}/video")
def recording_video(
    session_id: uuid.UUID,
    alias: Alias = Path(),
    start: AwareDatetime = Query(),
    duration_s: float = Query(gt=0, le=svc.MAX_PART_S),
    range_header: str | None = Header(None, alias="Range"),
    db: DBSession = Depends(get_db),
):
    """A recorded span (from list_recordings) as one MP4."""
    session = session_svc.get_session_or_404(session_id, db)
    windows = session_svc.recorded_windows(session.recording_intervals)
    try:
        # Exactly one of the parts list_recordings gives this Session: no other
        # path (e.g. one of mediamtx.yml's), nor another stretch of the camera
        listed = svc.is_listed_part(windows, camera_svc.list_cameras(db), alias, start, duration_s)
    except mediamtx.MediaMTXUnreachable:
        raise HTTPException(status_code=503, detail="The video service is not reachable")
    if not listed:
        raise HTTPException(status_code=404, detail="Not one of this session's recordings")

    try:
        path = svc.replay_file(alias, start, duration_s)
    except mediamtx.MediaMTXUnreachable:
        raise HTTPException(status_code=404, detail="Recording not available")
    # In byte ranges, which the player needs to seek
    return file_response(path, range_header, "video/mp4")
