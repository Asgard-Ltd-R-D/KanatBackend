import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.core.live import hub
from app.models import Session
from app.schemas.live import SessionUpdatedEvent
from app.schemas.session import SessionCreate, SessionListItem, SessionResponse, SessionUpdate
from app.services import camera_sync, detection
from app.services import cameras as camera_svc
from app.services import recordings as recording_svc
from app.services import sessions as svc

log = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _response(session: Session) -> SessionResponse:
    """The Session with its detection, which is held in memory."""
    response = SessionResponse.model_validate(session)
    response.detection = detection.state_of(session.id)
    return response


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(body: SessionCreate, background: BackgroundTasks, db: DBSession = Depends(get_db)):
    session = svc.create_session(body, db)
    # Starts the cameras recording if this Session records
    camera_sync.sync_soon(db)
    if session.camera_id is not None:
        alias = camera_svc.get_camera_or_404(session.camera_id, db).alias
        # Answered "starting" at once: the Run is asked for after the answer,
        # as it takes seconds to be watching
        detection.starting(session.id)
        background.add_task(detection.watch, session.id, alias)
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
        detection.end(svc.get_session_or_404(session_id, db))
    session = svc.update_session(session_id, body, db)
    # Ending a Session or switching its recording starts or stops the cameras recording
    camera_sync.sync_soon(db)
    hub.publish_from_thread(
        session_id,
        SessionUpdatedEvent(
            name=session.name, status=session.status, ended_at=session.ended_at, record=session.record
        ),
    )
    return _response(session)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    windows = svc.delete_session(session_id, db)
    # Stop the recording first if this Session was recording, then delete its
    # video: no Session is left to replay it
    camera_sync.sync_soon(db)
    others = svc.other_recorded_windows(session_id, db)
    # Deleting may wait for a replay download of the same part: the connection
    # goes back to the pool first
    db.close()
    try:
        recording_svc.delete_session_video(windows, others)
    except OSError:
        # The Session is already deleted; its files expire with MediaMTX's
        # recordDeleteAfter anyway
        log.exception("Deleting the video of session %s failed", session_id)
    return Response(status_code=204)
