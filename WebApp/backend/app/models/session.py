from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

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
        Index("uq_sessions_one_active", "status", unique=True, postgresql_where=text("status = 'active'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Whether the operator has recording on for this Session now; when it was on
    # is in recording_intervals
    record: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # The camera whose Stream the Session's Run watches, fixed at creation;
    # None without one, or once the camera is deleted
    camera_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True
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
