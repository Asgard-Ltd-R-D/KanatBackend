import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.locks import db_write
from app.models import Session
from app.repositories import sessions as repo
from app.schemas.session import SessionCreate, SessionListItem, SessionUpdate

log = logging.getLogger(__name__)


def get_session_or_404(session_id: uuid.UUID, db: DBSession) -> Session:
    session = repo.get(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def get_session_detail(session_id: uuid.UUID, db: DBSession) -> Session:
    """Load a session with only non-deleted bullet holes."""
    session = repo.get_with_bullets(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def list_sessions(db: DBSession) -> list[SessionListItem]:
    items = []
    for session, bullet_count in repo.list_with_bullet_counts(db):
        item = SessionListItem.model_validate(session)
        item.bullet_count = bullet_count
        items.append(item)
    return items


def _refuse_if_another_is_active(db: DBSession, session_id: uuid.UUID | None = None) -> None:
    """One active Session at a time: the operator completes it first. The
    database holds this too, when two requests race (uq_sessions_one_active)."""
    other = next((s for s in repo.list_active(db) if s.id != session_id), None)
    if other is not None:
        raise HTTPException(status_code=409, detail=_ANOTHER_ACTIVE.format(other.name))


def _refused_as_second_active(db: DBSession, session_id: uuid.UUID | None = None) -> HTTPException:
    """The database refused a second active Session: named if it is still
    active, else it completed in the meantime, and the operator tries again."""
    _refuse_if_another_is_active(db, session_id)
    return HTTPException(status_code=409, detail="Another Session was active: try again")


_ANOTHER_ACTIVE = "Session '{}' is still active: complete it first"
_NAME_TAKEN = "A Session named '{}' already exists: pick a different name"


def _refuse_if_name_taken(db: DBSession, name: str, session_id: uuid.UUID | None = None) -> None:
    """A Session's name is its own: two cannot share one. Checked trimmed and
    case-insensitively; session_id is the Session being renamed, not counted."""
    if repo.name_taken(db, name, session_id):
        raise HTTPException(status_code=409, detail=_NAME_TAKEN.format(name.strip()))


def refuse_if_name_rename_taken(session_id: uuid.UUID, body: SessionUpdate, db: DBSession) -> None:
    """A preflight for the router: refuse a rename onto another Session's name
    before the request takes any side effect (completing a Session ends its Runs
    first). _apply_update still checks under the write lock, for the race."""
    if body.name is not None:
        _refuse_if_name_taken(db, body.name, session_id)


def create_session(body: SessionCreate, db: DBSession) -> Session:
    # Serialized (db_write) like update_session: the name (and active) checks and
    # the insert are one step, so a create cannot race a rename onto the same name
    # — both passing their check before either commits — with no DB constraint to
    # catch it. SQLite is a single writer; this is the one backend process's lock.
    with db_write:
        _refuse_if_another_is_active(db)
        _refuse_if_name_taken(db, body.name)
        session = Session(
            id=uuid.uuid4(),
            name=body.name,
            status="active",
            started_at=datetime.now(timezone.utc),
        )
        try:
            session = repo.add(db, session)
        except repo.SecondActiveSession as e:
            raise _refused_as_second_active(db) from e
    log.info(
        "Session '%s' created", session.name,
        extra={"session_id": session.id, "session_name": session.name},
    )
    return session


def update_session(session_id: uuid.UUID, body: SessionUpdate, db: DBSession) -> Session:
    # Serialized (db_write): on SQLite get_for_update does not lock, so without
    # this two changes at once could both read the Session active and, e.g.,
    # both reopen it. The router's network call (detection_sync.ending) is
    # outside this, around the request.
    with db_write:
        session, before = _apply_update(session_id, body, db)
    _log_changes(session, before)
    return get_session_detail(session_id, db)


def _apply_update(session_id: uuid.UUID, body: SessionUpdate, db: DBSession) -> tuple[Session, dict]:
    session = repo.get_for_update(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    before = {"session_name": session.name, "status": session.status}
    if body.name is not None:
        _refuse_if_name_taken(db, body.name, session_id)
        session.name = body.name
    if body.status is not None:
        session.status = body.status
        if body.status == "completed" and session.ended_at is None:
            session.ended_at = datetime.now(timezone.utc)
        elif body.status == "active":
            if before["status"] != "active":
                _refuse_if_another_is_active(db, session_id)
            session.ended_at = None

    try:
        repo.save(db)
    except repo.SecondActiveSession as e:
        raise _refused_as_second_active(db, session_id) from e
    return session, before


def _log_changes(session: Session, before: dict) -> None:
    """One line for each thing that changed, in words an operator would use."""
    fields = {"session_id": session.id, "session_name": session.name}
    if session.status != before["status"]:
        if session.status == "completed":
            started = session.started_at
            duration_s = (session.ended_at - started).total_seconds() if session.ended_at and started else None
            log.info("Session '%s' completed", session.name, extra={**fields, "duration_s": duration_s})
        else:
            log.info("Session '%s' reopened", session.name, extra=fields)
    if session.name != before["session_name"]:
        log.info(
            "Session renamed from '%s' to '%s'", before["session_name"], session.name,
            extra={**fields, "previous_name": before["session_name"]},
        )


def delete_session(session_id: uuid.UUID, db: DBSession) -> None:
    """Deletes the Session and its Bullet Holes and Runs (cascade)."""
    with db_write:
        session = repo.get_for_update(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        name = session.name
        repo.delete(db, session)
    log.info(
        "Session '%s' deleted", name,
        extra={"session_id": session_id, "session_name": name},
    )
