import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.models import Session
from app.repositories import sessions as repo
from app.schemas.session import SessionCreate, SessionListItem, SessionUpdate


def get_session_or_404(session_id: uuid.UUID, db: DBSession) -> Session:
    session = repo.get(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def get_session_detail(session_id: uuid.UUID, db: DBSession) -> Session:
    """Load a session with only non-deleted bullet holes."""
    session = repo.get_with_bullets(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def list_sessions(db: DBSession) -> list[SessionListItem]:
    items = []
    for session, bullet_count in repo.list_with_bullet_counts(db):
        item = SessionListItem.model_validate(session)
        item.bullet_count = bullet_count
        items.append(item)
    return items


def create_session(body: SessionCreate, db: DBSession) -> Session:
    session = Session(
        id=uuid.uuid4(),
        name=body.name,
        status="active",
        started_at=datetime.now(timezone.utc),
        record=body.record,
    )
    return repo.add(db, session)


def update_session(session_id: uuid.UUID, body: SessionUpdate, db: DBSession) -> Session:
    session = get_session_or_404(session_id, db)

    if body.name is not None:
        session.name = body.name
    if body.record is not None:
        session.record = body.record
    if body.status is not None:
        session.status = body.status
        if body.status == "completed" and session.ended_at is None:
            session.ended_at = datetime.now(timezone.utc)
        elif body.status == "active":
            session.ended_at = None

    repo.save(db)
    return get_session_detail(session_id, db)


def delete_session(session_id: uuid.UUID, db: DBSession) -> tuple[datetime, datetime]:
    """Deletes the Session and returns the window it covered, so its video can
    be deleted too (routers/sessions.py)."""
    session = get_session_or_404(session_id, db)
    window = (session.started_at, session.ended_at or datetime.now(timezone.utc))
    repo.delete(db, session)
    return window


def session_windows(db: DBSession) -> list[tuple[datetime, datetime]]:
    """The window every remaining Session covers, an active one up to now."""
    now = datetime.now(timezone.utc)
    return [(s.started_at, s.ended_at or now) for s in repo.list_all(db)]
