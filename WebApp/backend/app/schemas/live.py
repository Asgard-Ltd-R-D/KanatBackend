import uuid
from datetime import datetime
from typing import Literal, Optional

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
    """Every field PATCH /sessions/{id} can change, so the event alone is enough
    to show it: the frontend stops listening as soon as a Session completes."""

    type: Literal["session_updated"] = "session_updated"
    name: str
    status: Literal["active", "completed"]
    ended_at: Optional[datetime]
    record: bool


LiveEvent = BulletCreatedEvent | BulletDeletedEvent | SessionUpdatedEvent
