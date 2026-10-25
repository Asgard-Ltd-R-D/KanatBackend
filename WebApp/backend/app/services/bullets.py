import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.models import BulletHole
from app.repositories import bullets as repo
from app.repositories import sessions as session_repo
from app.schemas.bullet_hole import BulletCreate

log = logging.getLogger(__name__)


def create_bullet(session_id: uuid.UUID, body: BulletCreate, db: DBSession) -> BulletHole:
    # Locked, so two bullets reported at once cannot take the same rank
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
            return dup

    bullet = BulletHole(
        id=uuid.uuid4(),
        session_id=session_id,
        first_seen_at=body.first_seen_at,
        position_x=body.position.x,
        position_y=body.position.y,
        target_index=body.target_index,
        x_mm=body.x_mm,
        y_mm=body.y_mm,
        source=body.source,
        idempotency_key=body.idempotency_key,
        rank=repo.count_active(db, session_id) + 1,
    )
    bullet = repo.add(db, bullet)
    delay_s = (datetime.now(timezone.utc) - bullet.first_seen_at).total_seconds()
    log.info(
        "Bullet Hole #%s received from %s", bullet.rank, "the model" if bullet.source == "model" else "the operator",
        extra={
            "session_id": session_id, "bullet_id": bullet.id, "rank": bullet.rank, "source": bullet.source,
            "x": bullet.position_x, "y": bullet.position_y, "target_index": bullet.target_index,
            "x_mm": bullet.x_mm, "y_mm": bullet.y_mm, "first_seen_at": bullet.first_seen_at,
            # From the model seeing it to the backend storing it
            "delay_s": round(delay_s, 3),
        },
    )
    return bullet


def delete_bullet(session_id: uuid.UUID, bullet_id: uuid.UUID, db: DBSession) -> None:
    session = session_repo.get_for_update(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    bullet = repo.get_active(db, session_id, bullet_id)
    if not bullet:
        raise HTTPException(status_code=404, detail="Bullet hole not found")

    # Soft delete; the bullets after it move up a rank
    bullet.deleted_at = datetime.now(timezone.utc)
    repo.move_up_after(db, session_id, bullet.rank)
    repo.save(db)
    log.info(
        "Bullet Hole #%s deleted by the operator", bullet.rank,
        extra={"session_id": session_id, "bullet_id": bullet_id, "rank": bullet.rank, "source": bullet.source},
    )
