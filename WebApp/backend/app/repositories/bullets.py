import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.models import BulletHole


def find_by_idempotency_key(db: DBSession, session_id: uuid.UUID, key: str) -> BulletHole | None:
    return db.query(BulletHole).filter(
        BulletHole.idempotency_key == key,
        BulletHole.session_id == session_id,
    ).first()


def count_active(db: DBSession, session_id: uuid.UUID) -> int:
    """How many of the Session's Bullet Holes are not deleted."""
    return db.query(func.count(BulletHole.id)).filter(
        BulletHole.session_id == session_id,
        BulletHole.deleted_at.is_(None),
    ).scalar()


def get_active(db: DBSession, session_id: uuid.UUID, bullet_id: uuid.UUID) -> BulletHole | None:
    """The Session's Bullet Hole, unless it is deleted."""
    return db.query(BulletHole).filter(
        BulletHole.id == bullet_id,
        BulletHole.session_id == session_id,
        BulletHole.deleted_at.is_(None),
    ).first()


def move_up_after(db: DBSession, session_id: uuid.UUID, rank: int) -> None:
    """Moves the Session's non-deleted Bullet Holes ranked after `rank` up one
    rank. Committed with the next save."""
    db.query(BulletHole).filter(
        BulletHole.session_id == session_id,
        BulletHole.deleted_at.is_(None),
        BulletHole.rank > rank,
    ).update({"rank": BulletHole.rank - 1}, synchronize_session=False)


def add(db: DBSession, bullet: BulletHole) -> BulletHole:
    db.add(bullet)
    db.commit()
    db.refresh(bullet)
    return bullet


def save(db: DBSession) -> None:
    """Commits the changes made to Bullet Holes loaded from `db`."""
    db.commit()
