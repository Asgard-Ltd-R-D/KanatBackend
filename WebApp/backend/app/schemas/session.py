import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bullet_hole import BulletHoleInSession


class SessionCreate(BaseModel):
    name: str


class SessionUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[Literal["active", "completed"]] = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    created_at: datetime
    bullet_holes: list[BulletHoleInSession] = Field(default=[], validation_alias="active_bullet_holes")


class SessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    created_at: datetime
    bullet_count: int = 0
