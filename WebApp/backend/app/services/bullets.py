import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.locks import db_write
from app.models import BulletHole
from app.repositories import bullets as repo
from app.repositories import sessions as session_repo
from app.schemas.bullet_hole import BulletCreate

log = logging.getLogger(__name__)


def create_bullet(session_id: uuid.UUID, body: BulletCreate, db: DBSession) -> tuple[BulletHole, int]:
    """The stored hole, and how many OTHER holes of its board changed rank because
    it was seen before them (0 for one that is the newest, or a retried one)."""
    # Serialized (db_write), so two bullets reported at once cannot read the same
    # count and take the same rank: on SQLite get_for_update does not lock
    with db_write:
        return _create_bullet(session_id, body, db)


def _create_bullet(session_id: uuid.UUID, body: BulletCreate, db: DBSession) -> tuple[BulletHole, int]:
    session = session_repo.get_for_update(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if body.source == "model" and session.status == "completed":
        log.warning(
            "Bullet Hole from the model refused: session %s is completed", session_id,
            extra={"session_id": session_id, "source": body.source, "first_seen_at": body.first_seen_at},
        )
        raise HTTPException(
            status_code=409,
            detail="Session is completed; model cannot add bullets to a closed session",
        )
    if body.source == "manual" and session.status == "active":
        log.warning(
            "Manual Bullet Hole refused: session %s is still active", session_id,
            extra={"session_id": session_id, "source": body.source},
        )
        raise HTTPException(
            status_code=409,
            detail="Session is still active; manual bullets can only be added after the session ends",
        )

    if body.idempotency_key is not None:
        dup = repo.find_by_idempotency_key(db, session_id, body.idempotency_key)
        if dup is not None:
            # The model retried a POST whose answer it did not get
            log.info(
                "Bullet Hole reported again, the stored one kept",
                extra={"session_id": session_id, "bullet_id": dup.id, "rank": dup.rank, "source": dup.source},
            )
            return dup, 0

    # A manual hole is stamped with the moment the backend stores it, not a time
    # the client sends: it is the newest on its board, so it ranks last
    first_seen_at = datetime.now(timezone.utc) if body.source == "manual" else body.first_seen_at
    bullet = BulletHole(
        id=uuid.uuid4(),
        session_id=session_id,
        camera_alias=body.camera,
        first_seen_at=first_seen_at,
        position_x=body.position.x,
        position_y=body.position.y,
        target_index=body.target_index,
        x_mm=body.x_mm,
        y_mm=body.y_mm,
        source=body.source,
        idempotency_key=body.idempotency_key,
        # Provisionally last, so a tie in time keeps the earlier arrival first; the
        # board is then ranked by when each hole was first seen
        rank=repo.count_active(db, session_id, body.camera) + 1,
    )
    bullet, renumbered = repo.add_in_time_order(db, bullet)
    delay_s = (datetime.now(timezone.utc) - bullet.first_seen_at).total_seconds()
    log.info(
        "Bullet Hole #%s received from %s", bullet.rank, "the model" if bullet.source == "model" else "the operator",
        extra={
            "session_id": session_id, "bullet_id": bullet.id, "rank": bullet.rank, "source": bullet.source,
            "x": bullet.position_x, "y": bullet.position_y, "target_index": bullet.target_index,
            "x_mm": bullet.x_mm, "y_mm": bullet.y_mm, "first_seen_at": bullet.first_seen_at,
            # From the model seeing it to the backend storing it
            "delay_s": round(delay_s, 3),
            # Other holes whose rank changed: some when it was seen before holes
            # already stored
            "renumbered": renumbered,
        },
    )
    return bullet, renumbered


def delete_bullet(session_id: uuid.UUID, bullet_id: uuid.UUID, db: DBSession) -> None:
    # Serialized (db_write) against create_bullet and other deletes, so the
    # renumbering of ranks after it is not lost to a concurrent write
    with db_write:
        _delete_bullet(session_id, bullet_id, db)


def _delete_bullet(session_id: uuid.UUID, bullet_id: uuid.UUID, db: DBSession) -> None:
    session = session_repo.get_for_update(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    bullet = repo.get_active(db, session_id, bullet_id)
    if not bullet:
        raise HTTPException(status_code=404, detail="Bullet hole not found")

    # Soft delete; the bullets after it on the same board move up a rank
    bullet.deleted_at = datetime.now(timezone.utc)
    repo.move_up_after(db, session_id, bullet.camera_alias, bullet.rank)
    repo.save(db)
    log.info(
        "Bullet Hole #%s deleted by the operator", bullet.rank,
        extra={"session_id": session_id, "bullet_id": bullet_id, "rank": bullet.rank, "source": bullet.source},
    )
