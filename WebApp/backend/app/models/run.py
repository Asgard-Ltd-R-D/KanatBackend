from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.types import UtcDateTime

if TYPE_CHECKING:
    from app.models.session import Session


class Run(Base):
    """A Run of the Detection Service that watched the Session, stored the
    first time the backend saw it watching (ADR-0009). It names its camera by
    alias, which also names the camera's recordings, so it keeps matching them
    once the camera is deleted."""

    __tablename__ = "runs"
    # A Run is told apart by its camera and its baseline frame's time: read
    # again, it is not stored again. A Session now has a Run per board, so the
    # camera is part of the key (two boards can take a baseline at the same instant)
    __table_args__ = (
        UniqueConstraint("session_id", "camera_alias", "taken_at", name="uq_runs_session_id_camera_alias_taken_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    camera_alias: Mapped[str] = mapped_column(String, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    # schemas/run.py's BaselineView, as JSON
    baseline_view: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Where it registered the Board, each schemas/run.py's Place as JSON, in
    # time order, starting with the baseline's: one kept only once it moved
    places: Mapped[list] = mapped_column(JSON, nullable=False)
    # Its latest Look's frame time the backend has read, registered or Lost
    watched_until: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    session: Mapped["Session"] = relationship("Session", back_populates="runs")
