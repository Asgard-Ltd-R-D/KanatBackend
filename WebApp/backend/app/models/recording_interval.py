from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.types import UtcDateTime

if TYPE_CHECKING:
    from app.models.session import Session


class RecordingInterval(Base):
    """A stretch of a Session with recording on: its replay and the video its
    deletion removes are the recordings within its intervals, not its whole
    time, since another Session may record while it does not."""

    __tablename__ = "recording_intervals"
    __table_args__ = (
        # One open interval per session at most (migration 005)
        Index(
            "uq_recording_intervals_one_open",
            "session_id",
            unique=True,
            sqlite_where=text("ended_at IS NULL"),
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    # None while recording
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    session: Mapped["Session"] = relationship("Session", back_populates="recording_intervals")
