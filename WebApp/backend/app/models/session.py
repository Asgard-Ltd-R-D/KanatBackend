from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.types import UtcDateTime

if TYPE_CHECKING:
    from app.models.bullet_hole import BulletHole
    from app.models.recording_interval import RecordingInterval
    from app.models.run import Run


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed')", name="ck_sessions_status"),
        # One active Session at a time (services/sessions.py checks it first,
        # with a message; this holds when two requests race)
        Index("uq_sessions_one_active", "status", unique=True,
              sqlite_where=text("status = 'active'"), postgresql_where=text("status = 'active'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    # Whether the operator has recording on for this Session now; when it was on
    # is in recording_intervals
    record: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    # The camera whose Stream the Session's Run watches, fixed at creation;
    # None without one, or once the camera is deleted
    camera_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True
    )

    bullet_holes: Mapped[list["BulletHole"]] = relationship(  # type: ignore[name-defined]
        "BulletHole",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="BulletHole.first_seen_at",
    )

    active_bullet_holes: Mapped[list["BulletHole"]] = relationship(  # type: ignore[name-defined]
        "BulletHole",
        primaryjoin="and_(Session.id == BulletHole.session_id, BulletHole.deleted_at == None)",
        foreign_keys="[BulletHole.session_id]",
        order_by="BulletHole.first_seen_at",
        viewonly=True,
        overlaps="bullet_holes,session",
    )

    recording_intervals: Mapped[list["RecordingInterval"]] = relationship(  # type: ignore[name-defined]
        "RecordingInterval",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="RecordingInterval.started_at",
    )

    runs: Mapped[list["Run"]] = relationship(  # type: ignore[name-defined]
        "Run",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Run.taken_at",
    )
