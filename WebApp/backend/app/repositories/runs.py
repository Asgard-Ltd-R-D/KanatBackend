import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DBSession

from app.models import Run


def add_once(db: DBSession, session_id: uuid.UUID, camera_alias: str, taken_at: datetime, baseline_view: dict,
             places: list[dict], watched_until: datetime) -> None:
    """Stores the Session's Run, unless one taken at the same time is already stored."""
    db.execute(
        insert(Run)
        .values(session_id=session_id, camera_alias=camera_alias, taken_at=taken_at, baseline_view=baseline_view,
                places=places, watched_until=watched_until)
        .on_conflict_do_nothing(constraint="uq_runs_session_id_taken_at")
    )
    db.commit()


def get_for_update(db: DBSession, session_id: uuid.UUID, taken_at: datetime) -> Run | None:
    """The Session's Run taken at `taken_at`, its row locked until commit:
    how far it watched is moved on under it."""
    return (db.query(Run).filter(Run.session_id == session_id, Run.taken_at == taken_at)
            .with_for_update().one_or_none())


def save(db: DBSession) -> None:
    """Commits the changes made to Runs loaded from `db`."""
    db.commit()
