import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.bullet_hole import BulletHoleInSession


class SessionCreate(BaseModel):
    name: str


class SessionUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    created_at: datetime
    bullet_holes: list[BulletHoleInSession] = []


class SessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    created_at: datetime
    bullet_count: int = 0
