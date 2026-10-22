import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bullet_hole import BulletHoleInSession


class Detection(BaseModel):
    """Whether a Run of the Detection Service watches the Session
    (services/detection.py). `none`: no camera, or no Run is wanted any more.
    `end_unconfirmed`: the Session completed without the Detection Service
    confirming it ended its Run, so Bullet Holes fired last may be missing."""

    state: Literal["none", "starting", "watching", "not_watching", "ending", "end_unconfirmed"]
    # Why not watching: the Detection Service did not answer, its Run failed
    # to start on the Stream, another Session's Run holds the service, or the
    # Session's camera was disabled or deleted. None for a Run lost while the
    # service answers, until its new start does
    reason: Optional[Literal["service_down", "stream_failed", "other_session", "camera_disabled"]] = None
    # The Detection Service's own words, when it refused the start
    detail: Optional[str] = None


class Group(BaseModel):
    """One Target's Group (the root CONTEXT.md), in millimetres from the
    Target's centre. Below two Bullet Holes every spread measure is None."""

    target_index: int
    n: int
    mpi_x_mm: float
    mpi_y_mm: float
    cep_mm: Optional[float] = None
    mean_radius_mm: Optional[float] = None
    rms_radius_mm: Optional[float] = None
    extreme_spread_mm: Optional[float] = None


class Grouping(BaseModel):
    """The Session's Groups, one per Target, in target_index order, and the
    Bullet Holes left out of every Group (services/groups.py)."""

    groups: list[Group] = []
    misses: int = 0
    # Manual ones, and detected ones without a print scale
    without_position: int = 0


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
    # Computed from bullet_holes: set by routers/sessions.py
    grouping: Grouping = Field(default_factory=Grouping)


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
