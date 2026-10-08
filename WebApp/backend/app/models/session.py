from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.bullet_hole import BulletHole


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed')", name="ck_sessions_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True
    )

    bullet_holes: Mapped[list[BulletHole]] = relationship(
        "BulletHole",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="BulletHole.first_seen_at",
    )

    active_bullet_holes: Mapped[list[BulletHole]] = relationship(
        "BulletHole",
        primaryjoin="and_(Session.id == BulletHole.session_id, BulletHole.deleted_at == None)",
        foreign_keys="[BulletHole.session_id]",
        order_by="BulletHole.first_seen_at",
        viewonly=True,
        overlaps="bullet_holes,session",
    )
