import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.core.live import hub
from app.models import Session
from app.schemas.live import SessionUpdatedEvent
from app.schemas.session import SessionCreate, SessionListItem, SessionResponse, SessionUpdate
from app.services import camera_sync, detection_sync, groups
from app.services import cameras as camera_svc
from app.services import sessions as svc

log = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _response(session: Session) -> SessionResponse:
    """The Session with its per-board detection, which is held in memory, and
    its per-board Groups."""
    response = SessionResponse.model_validate(session)
    response.detections = detection_sync.boards_of(session.id)
    response.groupings = groups.groupings(response.bullet_holes)
    return response


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(body: SessionCreate, background: BackgroundTasks, db: DBSession = Depends(get_db)):
    session = svc.create_session(body, db)
    camera_sync.sync_soon(db)
    # The Session spans every enabled camera, one board each: answered "starting"
    # at once, each Run asked for after the answer, as it takes seconds to watch.
    # The Runs are asked for together (watch_all), so a slow or unavailable camera
    # does not hold up detection on the others.
    aliases = [camera.alias for camera in camera_svc.list_cameras(db) if camera.enabled]
    for alias in aliases:
        detection_sync.starting(session.id, alias)
    background.add_task(detection_sync.watch_all, session.id, aliases)
    return _response(session)


@router.get("", response_model=list[SessionListItem])
def list_sessions(db: DBSession = Depends(get_db)):
    return svc.list_sessions(db)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    return _response(svc.get_session_detail(session_id, db))


@router.patch("/{session_id}", response_model=SessionResponse)
def update_session(session_id: uuid.UUID, body: SessionUpdate, db: DBSession = Depends(get_db)):
    if body.status == "completed":
        # Its Run ends first, the Session still active, so the Bullet Holes
        # it posts on the way out are stored
        with detection_sync.ending(svc.get_session_or_404(session_id, db)):
            session = svc.update_session(session_id, body, db)
    else:
        session = svc.update_session(session_id, body, db)
    if body.status == "active":
        detection_sync.reopened(session_id)
    camera_sync.sync_soon(db)
    hub.publish_from_thread(
        session_id,
        SessionUpdatedEvent(name=session.name, status=session.status, ended_at=session.ended_at),
    )
    return _response(session)


@router.post("/{session_id}/baseline/{camera}", response_model=SessionResponse)
def retake_baseline(session_id: uuid.UUID, camera: str, background: BackgroundTasks, db: DBSession = Depends(get_db)):
    """A new Run for one of the active Session's boards, from a fresh baseline:
    after that board's Target Sheet is re-hung. Answered `starting` at once;
    `watching` only once the new Run's baseline is built."""
    session = svc.get_session_or_404(session_id, db)
    camera_row = next((c for c in camera_svc.list_cameras(db) if c.alias == camera), None)
    if session.status != "active" or camera_row is None or not camera_row.enabled:
        raise HTTPException(status_code=409, detail="Only a board of an active Session watched by an enabled camera has a baseline")
    if not detection_sync.retaking_baseline(session.id, camera):
        raise HTTPException(status_code=409, detail="Detection is already starting or ending on this board: try again")
    log.info("Retaking the baseline of session %s board %s", session.id, camera)
    background.add_task(detection_sync.retake_baseline, session.id, camera)
    return _response(session)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    # Its Runs end first: nothing is left for them to post into
    with detection_sync.ending(svc.get_session_or_404(session_id, db)):
        svc.delete_session(session_id, db)
    return Response(status_code=204)
