import math
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class BulletPosition(BaseModel):
    x: float = Field(ge=0, le=1405)
    y: float = Field(ge=0, le=1120)


class BulletCreate(BaseModel):
    version: str
    first_seen_at: AwareDatetime
    position: BulletPosition
    target_index: Optional[int] = None
    x_mm: Optional[float] = None
    y_mm: Optional[float] = None
    source: Literal["model", "manual"] = "model"

    @field_validator("version")
    @classmethod
    def version_must_be_v1(cls, v: str) -> str:
        if v != "v1":
            raise ValueError(f"Unsupported contract version '{v}', expected 'v1'")
        return v

    @field_validator("x_mm", "y_mm")
    @classmethod
    def must_be_finite(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("must be a finite number, not NaN or infinity")
        return v


class BulletHoleInSession(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    rank: int
    first_seen_at: datetime
    position_x: float
    position_y: float
    target_index: Optional[int]
    x_mm: Optional[float]
    y_mm: Optional[float]
    source: str
    created_at: datetime


class BulletHoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    rank: int
    first_seen_at: datetime
    position_x: float
    position_y: float
    target_index: Optional[int]
    x_mm: Optional[float]
    y_mm: Optional[float]
    source: str
    created_at: datetime
