import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.models import BulletHole
from app.repositories import bullets as repo
from app.repositories import sessions as session_repo
from app.schemas.bullet_hole import BulletCreate


def create_bullet(session_id: uuid.UUID, body: BulletCreate, db: DBSession) -> BulletHole:
    # Locked, so two bullets reported at once cannot take the same rank
    session = session_repo.get_for_update(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if body.source == "model" and session.status == "completed":
        raise HTTPException(
            status_code=409,
            detail="Session is completed; model cannot add bullets to a closed session",
        )
    if body.source == "manual" and session.status == "active":
        raise HTTPException(
            status_code=409,
            detail="Session is still active; manual bullets can only be added after the session ends",
        )

    if body.idempotency_key is not None:
        dup = repo.find_by_idempotency_key(db, session_id, body.idempotency_key)
        if dup is not None:
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
    return repo.add(db, bullet)


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
