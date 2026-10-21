import logging
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.core.live import hub
from app.schemas.live import SessionUpdatedEvent
from app.schemas.session import SessionCreate, SessionListItem, SessionResponse, SessionUpdate
from app.services import camera_sync
from app.services import recordings as recording_svc
from app.services import sessions as svc

log = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(body: SessionCreate, db: DBSession = Depends(get_db)):
    session = svc.create_session(body, db)
    # Starts the cameras recording if this Session records
    camera_sync.sync_soon(db)
    return session


@router.get("", response_model=list[SessionListItem])
def list_sessions(db: DBSession = Depends(get_db)):
    return svc.list_sessions(db)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    return svc.get_session_detail(session_id, db)


@router.patch("/{session_id}", response_model=SessionResponse)
def update_session(session_id: uuid.UUID, body: SessionUpdate, db: DBSession = Depends(get_db)):
    session = svc.update_session(session_id, body, db)
    # Ending a Session or switching its recording starts or stops the cameras recording
    camera_sync.sync_soon(db)
    hub.publish_from_thread(
        session_id,
        SessionUpdatedEvent(
            name=session.name, status=session.status, ended_at=session.ended_at, record=session.record
        ),
    )
    return session


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    windows = svc.delete_session(session_id, db)
    # Stop the recording first if this Session was recording, then delete its
    # video: no Session is left to replay it
    camera_sync.sync_soon(db)
    try:
        recording_svc.delete_session_video(windows, svc.other_recorded_windows(session_id, db))
    except OSError:
        # The Session is already deleted; its files expire with MediaMTX's
        # recordDeleteAfter anyway
        log.exception("Deleting the video of session %s failed", session_id)
    return Response(status_code=204)
