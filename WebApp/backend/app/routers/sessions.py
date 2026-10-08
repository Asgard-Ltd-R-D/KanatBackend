import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.schemas.session import SessionCreate, SessionListItem, SessionResponse, SessionUpdate
from app.services import sessions as svc

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(body: SessionCreate, db: DBSession = Depends(get_db)):
    return svc.create_session(body, db)


@router.get("", response_model=list[SessionListItem])
def list_sessions(db: DBSession = Depends(get_db)):
    return svc.list_sessions(db)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    return svc.get_session_detail(session_id, db)


@router.patch("/{session_id}", response_model=SessionResponse)
def update_session(session_id: uuid.UUID, body: SessionUpdate, db: DBSession = Depends(get_db)):
    return svc.update_session(session_id, body, db)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: uuid.UUID, db: DBSession = Depends(get_db)):
    svc.delete_session(session_id, db)
    return Response(status_code=204)
