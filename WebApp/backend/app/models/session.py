from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Index, String, Uuid, event, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.logs import forget_session, remember_session
from app.core.types import UtcDateTime

if TYPE_CHECKING:
    from app.models.bullet_hole import BulletHole
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
    # A Session spans every enabled camera: it has no single camera. Which
    # boards it watched is in its Runs and its Bullet Holes' camera_alias
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True
    )

    bullet_holes: Mapped[list["BulletHole"]] = relationship(  # type: ignore[name-defined]
        "BulletHole",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="BulletHole.first_seen_at, BulletHole.rank",
    )

    active_bullet_holes: Mapped[list["BulletHole"]] = relationship(  # type: ignore[name-defined]
        "BulletHole",
        primaryjoin="and_(Session.id == BulletHole.session_id, BulletHole.deleted_at == None)",
        foreign_keys="[BulletHole.session_id]",
        order_by="BulletHole.first_seen_at, BulletHole.rank",
        viewonly=True,
        overlaps="bullet_holes,session",
    )

    runs: Mapped[list["Run"]] = relationship(  # type: ignore[name-defined]
        "Run",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Run.taken_at",
    )


# Keeps the log's id -> name list (core/logs.py) current, so every line that names
# a Session by its id can say its name too
@event.listens_for(Session, "load")
def _loaded(target: Session, context) -> None:
    remember_session(target.id, target.name)


@event.listens_for(Session, "refresh")
def _refreshed(target: Session, context, attrs) -> None:
    remember_session(target.id, target.name)


@event.listens_for(Session, "after_insert")
@event.listens_for(Session, "after_update")
def _saved(mapper, connection, target: Session) -> None:
    remember_session(target.id, target.name)


@event.listens_for(Session, "after_delete")
def _deleted(mapper, connection, target: Session) -> None:
    forget_session(target.id)
