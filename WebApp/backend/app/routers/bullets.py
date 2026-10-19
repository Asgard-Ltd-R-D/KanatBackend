import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_db
from app.core.live import hub
from app.schemas.bullet_hole import BulletCreate, BulletHoleInSession, BulletHoleResponse
from app.schemas.live import BulletCreatedEvent, BulletDeletedEvent
from app.services import bullets as svc

router = APIRouter(prefix="/sessions/{session_id}/bullets", tags=["bullets"])


@router.post("", response_model=BulletHoleResponse, status_code=201)
def report_bullet(session_id: uuid.UUID, body: BulletCreate, db: DBSession = Depends(get_db)):
    bullet = svc.create_bullet(session_id, body, db)
    # A retried POST returns the existing bullet; publishing it again is harmless,
    # the frontend keys bullets by id
    hub.publish_from_thread(
        session_id, BulletCreatedEvent(bullet=BulletHoleInSession.model_validate(bullet))
    )
    return bullet


@router.delete("/{bullet_id}", status_code=204)
def delete_bullet(session_id: uuid.UUID, bullet_id: uuid.UUID, db: DBSession = Depends(get_db)):
    svc.delete_bullet(session_id, bullet_id, db)
    hub.publish_from_thread(session_id, BulletDeletedEvent(bullet_id=bullet_id))
    return Response(status_code=204)
