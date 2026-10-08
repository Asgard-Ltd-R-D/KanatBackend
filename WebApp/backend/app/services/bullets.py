import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.models import BulletHole
from app.schemas.bullet_hole import BulletCreate
from app.services.sessions import get_session_or_404


def create_bullet(session_id: uuid.UUID, body: BulletCreate, db: DBSession) -> BulletHole:
    session = get_session_or_404(session_id, db)

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

    existing = db.query(func.count(BulletHole.id)).filter(
        BulletHole.session_id == session_id,
        BulletHole.deleted_at.is_(None),
    ).scalar()

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
        rank=existing + 1,
    )
    db.add(bullet)
    db.commit()
    db.refresh(bullet)
    return bullet


def delete_bullet(session_id: uuid.UUID, bullet_id: uuid.UUID, db: DBSession) -> None:
    get_session_or_404(session_id, db)

    bullet = db.query(BulletHole).filter(
        BulletHole.id == bullet_id,
        BulletHole.session_id == session_id,
        BulletHole.deleted_at.is_(None),
    ).first()

    if not bullet:
        raise HTTPException(status_code=404, detail="Bullet hole not found")

    deleted_rank = bullet.rank
    bullet.deleted_at = datetime.now(timezone.utc)

    db.query(BulletHole).filter(
        BulletHole.session_id == session_id,
        BulletHole.deleted_at.is_(None),
        BulletHole.rank > deleted_rank,
    ).update({"rank": BulletHole.rank - 1}, synchronize_session=False)

    db.commit()
