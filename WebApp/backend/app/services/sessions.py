import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session as DBSession, selectinload

from app.models import BulletHole, Session
from app.schemas.session import SessionCreate, SessionListItem, SessionUpdate


def get_session_or_404(session_id: uuid.UUID, db: DBSession) -> Session:
    session = db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def get_session_detail(session_id: uuid.UUID, db: DBSession) -> Session:
    """Load a session with only non-deleted bullet holes."""
    stmt = (
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.bullet_holes.and_(BulletHole.deleted_at.is_(None))))
    )
    session = db.scalar(stmt)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def list_sessions(db: DBSession) -> list[SessionListItem]:
    rows = (
        db.query(
            Session,
            func.count(BulletHole.id).label("bullet_count"),
        )
        .outerjoin(
            BulletHole,
            and_(BulletHole.session_id == Session.id, BulletHole.deleted_at.is_(None)),
        )
        .group_by(Session.id)
        .order_by(Session.created_at.desc())
        .all()
    )

    items = []
    for session, bullet_count in rows:
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
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def update_session(session_id: uuid.UUID, body: SessionUpdate, db: DBSession) -> Session:
    session = get_session_or_404(session_id, db)

    if body.name is not None:
        session.name = body.name
    if body.status is not None:
        session.status = body.status
        if body.status == "completed" and session.ended_at is None:
            session.ended_at = datetime.now(timezone.utc)

    db.commit()
    return get_session_detail(session_id, db)


def delete_session(session_id: uuid.UUID, db: DBSession) -> None:
    session = get_session_or_404(session_id, db)
    db.delete(session)
    db.commit()
