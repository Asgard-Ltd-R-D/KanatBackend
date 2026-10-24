from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.session import Session


class Run(Base):
    """A Run of the Detection Service that watched the Session, stored the
    first time the backend saw it watching (ADR-0009). It names its camera by
    alias, which also names the camera's recordings, so it keeps matching them
    once the camera is deleted."""

    __tablename__ = "runs"
    # A Run is told apart by its baseline frame's time: read again, it is not stored again
    __table_args__ = (UniqueConstraint("session_id", "taken_at", name="uq_runs_session_id_taken_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    camera_alias: Mapped[str] = mapped_column(String, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # schemas/run.py's BaselineView, as JSON
    baseline_view: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Where it registered the Board, each schemas/run.py's Place as JSON, in
    # time order, starting with the baseline's: one kept only once it moved
    places: Mapped[list] = mapped_column(JSONB, nullable=False)
    # Its latest Look's frame time the backend has read, registered or Lost
    watched_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped["Session"] = relationship("Session", back_populates="runs")
