import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas.bullet_hole import BulletHoleInSession


# Events pushed to the frontends watching a Session, as Server-Sent Events from
# /sessions/{id}/live (routers/live.py)


class BulletCreatedEvent(BaseModel):
    type: Literal["bullet_created"] = "bullet_created"
    bullet: BulletHoleInSession


class BulletDeletedEvent(BaseModel):
    type: Literal["bullet_deleted"] = "bullet_deleted"
    bullet_id: uuid.UUID


class SessionUpdatedEvent(BaseModel):
    type: Literal["session_updated"] = "session_updated"
    status: Literal["active", "completed"]


LiveEvent = BulletCreatedEvent | BulletDeletedEvent | SessionUpdatedEvent
