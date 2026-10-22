import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bullet_hole import BulletHoleInSession


class Detection(BaseModel):
    """Whether a Run of the Detection Service watches the Session
    (services/detection.py). `none`: no camera, or no Run is wanted any more."""

    state: Literal["none", "starting", "watching", "not_watching", "ending"]
    # Why not watching: the Detection Service did not answer, its Run failed
    # to start on the Stream, another Session's Run holds the service, or the
    # Session's camera was disabled or deleted. None for a Run lost while the
    # service answers, until its new start does
    reason: Optional[Literal["service_down", "stream_failed", "other_session", "camera_disabled"]] = None
    # The Detection Service's own words, when it refused the start
    detail: Optional[str] = None


class SessionCreate(BaseModel):
    name: str
    record: bool = False
    # An enabled camera, whose Stream a Run then watches; fixed for the
    # Session's life, so every Bullet Hole is placed from one baseline
    camera_id: Optional[uuid.UUID] = None


class SessionUpdate(BaseModel):
    # Unknown fields are refused, camera_id among them: it cannot change
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    status: Optional[Literal["active", "completed"]] = None
    record: Optional[bool] = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    record: bool
    camera_id: Optional[uuid.UUID]
    created_at: datetime
    bullet_holes: list[BulletHoleInSession] = Field(default=[], validation_alias="active_bullet_holes")
    # Held in memory, not in the database: set by routers/sessions.py
    detection: Detection = Field(default_factory=lambda: Detection(state="none"))


class SessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    record: bool
    created_at: datetime
    bullet_count: int = 0
