import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session as DBSession, selectinload

from app.models import BulletHole, Session


def get(db: DBSession, session_id: uuid.UUID) -> Session | None:
    return db.get(Session, session_id)


def get_for_update(db: DBSession, session_id: uuid.UUID) -> Session | None:
    """The Session, its row locked until commit: bullets are ranked under it."""
    return db.query(Session).filter(Session.id == session_id).with_for_update().first()


def get_with_bullets(db: DBSession, session_id: uuid.UUID) -> Session | None:
    """The Session with only its non-deleted Bullet Holes loaded."""
    stmt = (
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.bullet_holes.and_(BulletHole.deleted_at.is_(None))))
    )
    return db.scalar(stmt)


def list_with_bullet_counts(db: DBSession) -> list[tuple[Session, int]]:
    """Every Session, newest first, with its count of non-deleted Bullet Holes."""
    return (
        db.query(Session, func.count(BulletHole.id).label("bullet_count"))
        .outerjoin(BulletHole, and_(BulletHole.session_id == Session.id, BulletHole.deleted_at.is_(None)))
        .group_by(Session.id)
        .order_by(Session.created_at.desc())
        .all()
    )


def add(db: DBSession, session: Session) -> Session:
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def save(db: DBSession) -> None:
    """Commits the changes made to Sessions loaded from `db`."""
    db.commit()


def delete(db: DBSession, session: Session) -> None:
    db.delete(session)
    db.commit()
