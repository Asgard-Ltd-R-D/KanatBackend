import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.models import BulletHole


def find_by_idempotency_key(db: DBSession, session_id: uuid.UUID, key: str) -> BulletHole | None:
    return db.query(BulletHole).filter(
        BulletHole.idempotency_key == key,
        BulletHole.session_id == session_id,
    ).first()


def count_active(db: DBSession, session_id: uuid.UUID, camera_alias: str | None) -> int:
    """How many of the Session's Bullet Holes on this board are not deleted.
    Ranks run per board, so each board's log numbers from 1."""
    return db.query(func.count(BulletHole.id)).filter(
        BulletHole.session_id == session_id,
        BulletHole.camera_alias.is_(camera_alias) if camera_alias is None else BulletHole.camera_alias == camera_alias,
        BulletHole.deleted_at.is_(None),
    ).scalar()


def get_active(db: DBSession, session_id: uuid.UUID, bullet_id: uuid.UUID) -> BulletHole | None:
    """The Session's Bullet Hole, unless it is deleted."""
    return db.query(BulletHole).filter(
        BulletHole.id == bullet_id,
        BulletHole.session_id == session_id,
        BulletHole.deleted_at.is_(None),
    ).first()


def move_up_after(db: DBSession, session_id: uuid.UUID, camera_alias: str | None, rank: int) -> None:
    """Moves this board's non-deleted Bullet Holes ranked after `rank` up one
    rank. Ranks run per board, so only the same board's holes move. Committed
    with the next save."""
    db.query(BulletHole).filter(
        BulletHole.session_id == session_id,
        BulletHole.camera_alias.is_(camera_alias) if camera_alias is None else BulletHole.camera_alias == camera_alias,
        BulletHole.deleted_at.is_(None),
        BulletHole.rank > rank,
    ).update({"rank": BulletHole.rank - 1}, synchronize_session=False)


def renumber_board(db: DBSession, session_id: uuid.UUID, camera_alias: str | None,
                   skip: uuid.UUID | None = None) -> int:
    """Ranks this board's non-deleted Bullet Holes 1..n by when each was first
    seen (`first_seen_at`), the older rank breaking a tie, so a shot confirmed
    late but seen early takes its place among the earlier ones. Only holes whose
    rank changes are written. Answers how many changed, the hole `skip` (the one
    just added, whose rank is its own news) not counted. Committed with the next save."""
    holes = db.query(BulletHole).filter(
        BulletHole.session_id == session_id,
        BulletHole.camera_alias.is_(camera_alias) if camera_alias is None else BulletHole.camera_alias == camera_alias,
        BulletHole.deleted_at.is_(None),
    # populate_existing: read the ranks as stored, not as a hole already loaded
    # in this session remembers them (move_up_after updates in bulk)
    ).order_by(BulletHole.first_seen_at, BulletHole.rank).populate_existing().all()
    changed = 0
    for rank, hole in enumerate(holes, start=1):
        if hole.rank != rank:
            hole.rank = rank
            if hole.id != skip:
                changed += 1
    return changed


def add_in_time_order(db: DBSession, bullet: BulletHole) -> tuple[BulletHole, int]:
    """Stores the hole, then renumbers its board by `first_seen_at`, in one
    commit: no reader sees it ranked before the others have moved. Answers the
    hole and how many OTHER holes have a new rank."""
    db.add(bullet)
    db.flush()
    changed = renumber_board(db, bullet.session_id, bullet.camera_alias, skip=bullet.id)
    db.commit()
    db.refresh(bullet)
    return bullet, changed


def save(db: DBSession) -> None:
    """Commits the changes made to Bullet Holes loaded from `db`."""
    db.commit()
