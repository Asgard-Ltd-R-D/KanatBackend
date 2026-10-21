import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.models import RecordingInterval, Session
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


def _follow_recording(session: Session, now: datetime) -> None:
    """Opens a recording interval when the Session starts recording, and closes
    it when recording goes off or the Session ends."""
    open_interval = next((i for i in session.recording_intervals if i.ended_at is None), None)
    recording = session.record and session.status == "active"
    if recording and open_interval is None:
        session.recording_intervals.append(RecordingInterval(id=uuid.uuid4(), started_at=now))
    elif not recording and open_interval is not None:
        open_interval.ended_at = session.ended_at or now


def create_session(body: SessionCreate, db: DBSession) -> Session:
    session = Session(
        id=uuid.uuid4(),
        name=body.name,
        status="active",
        started_at=datetime.now(timezone.utc),
        record=body.record,
    )
    _follow_recording(session, session.started_at)
    return repo.add(db, session)


def update_session(session_id: uuid.UUID, body: SessionUpdate, db: DBSession) -> Session:
    # Locked until commit, so two changes at once cannot both see no open
    # recording interval and each open one
    session = repo.get_for_update(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
    _follow_recording(session, datetime.now(timezone.utc))

    repo.save(db)
    return get_session_detail(session_id, db)


def recorded_windows(intervals: list[RecordingInterval]) -> list[tuple[datetime, datetime]]:
    """The intervals as (start, end), an open one up to now."""
    now = datetime.now(timezone.utc)
    return [(i.started_at, i.ended_at or now) for i in intervals]


def delete_session(session_id: uuid.UUID, db: DBSession) -> list[tuple[datetime, datetime]]:
    """Deletes the Session and returns the windows it recorded, so its video
    can be deleted too (routers/sessions.py)."""
    session = get_session_or_404(session_id, db)
    windows = recorded_windows(session.recording_intervals)
    repo.delete(db, session)
    return windows


def other_recorded_windows(session_id: uuid.UUID, db: DBSession) -> list[tuple[datetime, datetime]]:
    """What every other Session recorded."""
    return recorded_windows(repo.intervals_of_other_sessions(db, session_id))
