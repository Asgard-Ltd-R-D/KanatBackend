from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.types import UtcDateTime

if TYPE_CHECKING:
    from app.models.session import Session


class BulletHole(Base):
    __tablename__ = "bullet_holes"
    __table_args__ = (
        # Partial unique index: allows many NULLs (legacy / manual bullets),
        # but enforces uniqueness when a key is present.
        Index(
            "uq_bullet_holes_session_idempotency_key",
            "session_id", "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    position_x: Mapped[float] = mapped_column(Float, nullable=False)
    position_y: Mapped[float] = mapped_column(Float, nullable=False)
    target_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    x_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="model")
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    session: Mapped[Session] = relationship("Session", back_populates="bullet_holes")
