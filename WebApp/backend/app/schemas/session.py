import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bullet_hole import BulletHoleInSession
from app.schemas.run import RunResponse


class Detection(BaseModel):
    """Whether a Run of the Detection Service watches the Session
    (services/detection_sync.py). `none`: no camera, or no Run is wanted any more.
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
    """One board's Groups, one per Target, in target_index order, and the
    Bullet Holes left out of every Group (services/groups.py)."""

    groups: list[Group] = []
    misses: int = 0
    # Manual ones, and detected ones without a print scale
    without_position: int = 0


class BoardDetection(BaseModel):
    """Whether a Run watches one of the Session's boards, named by its camera."""

    camera_alias: str
    detection: Detection


class BoardGrouping(BaseModel):
    """One board's Grouping, named by its camera; camera_alias None is the
    holes on no board (manual ones in a Session with no camera)."""

    camera_alias: Optional[str] = None
    grouping: Grouping


class SessionCreate(BaseModel):
    name: str
    record: bool = False


class SessionUpdate(BaseModel):
    # Unknown fields are refused: a Session's name, status and recording change,
    # nothing else
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
    created_at: datetime
    bullet_holes: list[BulletHoleInSession] = Field(default=[], validation_alias="active_bullet_holes")
    # Each Run that watched it, any board, in taken_at order
    runs: list[RunResponse] = []
    # One per enabled camera (board): held in memory, set by routers/sessions.py
    detections: list[BoardDetection] = []
    # One per board the holes are on: computed from bullet_holes by routers/sessions.py
    groupings: list[BoardGrouping] = []


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
