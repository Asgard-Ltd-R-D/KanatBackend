"""The schema on a real database: the migration, and the rules only the
database keeps. Runs on a throwaway SQLite file (the app's database), so it
needs no server. The engines use the app's own SQLite settings (core/database.py)
so foreign keys are enforced, as they are at runtime."""
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from alembic import command
from app.config.settings import settings
from app.core.database import _make_engine
from app.repositories import sessions as sessions_repo
from app.schemas.session import SessionCreate, SessionUpdate
from app.services import cameras as camera_svc
from app.services import sessions as sessions_svc


def alembic_config():
    # No config file name, so env.py leaves the test run's logging alone
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    return config


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    """A fresh empty SQLite database's URL, which alembic's env.py reads from
    settings, migrated to head."""
    url = f"sqlite:///{tmp_path / 'kanat_test.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    command.upgrade(alembic_config(), "head")
    return url


def schema(url):
    """The sessions and bullet_holes columns, whether the runs table exists,
    and the names of the runs table's unique constraints."""
    engine = _make_engine(url)
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        sessions = {c["name"] for c in inspector.get_columns("sessions")} if "sessions" in tables else set()
        holes = {c["name"] for c in inspector.get_columns("bullet_holes")} if "bullet_holes" in tables else set()
        runs = {uc["name"] for uc in inspector.get_unique_constraints("runs")} if "runs" in tables else None
        return sessions, holes, runs
    finally:
        engine.dispose()


def test_the_migration_applies_and_reverses_cleanly(db_url):
    config = alembic_config()

    sessions, holes, run_constraints = schema(db_url)       # migrated to head by the fixture
    # The single chosen camera is gone; each hole names the board it is on,
    # and a Run's identity gained its camera
    assert "camera_id" not in sessions
    assert "camera_alias" in holes
    assert run_constraints == {"uq_runs_session_id_camera_alias_taken_at"}

    command.downgrade(config, "base")
    assert schema(db_url) == (set(), set(), None)           # every table dropped

    command.upgrade(config, "head")
    sessions, holes, run_constraints = schema(db_url)
    assert "camera_id" not in sessions and "camera_alias" in holes
    assert run_constraints == {"uq_runs_session_id_camera_alias_taken_at"}


def test_the_migration_backfills_the_board_from_the_old_camera(tmp_path, monkeypatch):
    """Before sessions.camera_id is dropped, each hole's board (camera_alias) is
    backfilled from its Session's old camera, so a Session that watched one
    camera keeps reading as a one-board Session."""
    url = f"sqlite:///{tmp_path / 'kanat_backfill.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    config = alembic_config()
    command.upgrade(config, "a1b2c3d4e5f6")   # the revision before Sessions spanned every camera

    camera_id, session_id, hole_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    engine = _make_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cameras (id, alias, mcast_ip, mcast_port) VALUES (:id, 'lane7', '226.226.226.112', 112)"
        ), {"id": camera_id.hex})
        conn.execute(text(
            "INSERT INTO sessions (id, name, status, started_at, camera_id) "
            "VALUES (:id, 'Range 1', 'completed', CURRENT_TIMESTAMP, :camera)"
        ), {"id": session_id.hex, "camera": camera_id.hex})
        conn.execute(text(
            "INSERT INTO bullet_holes (id, session_id, first_seen_at, position_x, position_y, source, rank) "
            "VALUES (:id, :session, CURRENT_TIMESTAMP, 700, 560, 'model', 1)"
        ), {"id": hole_id.hex, "session": session_id.hex})
    engine.dispose()

    command.upgrade(config, "head")

    engine = _make_engine(url)
    with engine.connect() as conn:
        alias = conn.execute(text("SELECT camera_alias FROM bullet_holes WHERE id = :id"), {"id": hole_id.hex}).scalar()
    engine.dispose()
    assert alias == "lane7"


def test_the_migration_backfills_the_board_from_a_saved_run_when_the_camera_was_deleted(tmp_path, monkeypatch):
    """A camera deleted before the upgrade left sessions.camera_id NULL, so the
    hole's board cannot come from the camera join; it is recovered from the
    Session's saved run, keeping the hole on its board instead of 'no board'."""
    url = f"sqlite:///{tmp_path / 'kanat_backfill_run.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    config = alembic_config()
    command.upgrade(config, "a1b2c3d4e5f6")   # the revision before Sessions spanned every camera

    session_id, hole_id, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    engine = _make_engine(url)
    with engine.begin() as conn:
        # The camera is gone: sessions.camera_id is NULL (ON DELETE SET NULL)
        conn.execute(text(
            "INSERT INTO sessions (id, name, status, started_at, camera_id) "
            "VALUES (:id, 'Range 1', 'completed', CURRENT_TIMESTAMP, NULL)"
        ), {"id": session_id.hex})
        conn.execute(text(
            "INSERT INTO runs (id, session_id, camera_alias, taken_at, baseline_view, places, watched_until) "
            "VALUES (:id, :session, 'lane7', CURRENT_TIMESTAMP, '{}', '[]', CURRENT_TIMESTAMP)"
        ), {"id": run_id.hex, "session": session_id.hex})
        conn.execute(text(
            "INSERT INTO bullet_holes (id, session_id, first_seen_at, position_x, position_y, source, rank) "
            "VALUES (:id, :session, CURRENT_TIMESTAMP, 700, 560, 'model', 1)"
        ), {"id": hole_id.hex, "session": session_id.hex})
    engine.dispose()

    command.upgrade(config, "head")

    engine = _make_engine(url)
    with engine.connect() as conn:
        alias = conn.execute(text("SELECT camera_alias FROM bullet_holes WHERE id = :id"), {"id": hole_id.hex}).scalar()
    engine.dispose()
    assert alias == "lane7"


def test_deleting_a_camera_leaves_its_sessions_and_holes_untouched(db_url):
    """Sessions no longer reference a camera, and a hole's board is a plain
    alias, not a foreign key: deleting a camera touches neither."""
    engine = _make_engine(db_url)
    camera_id, session_id, hole_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cameras (id, alias, mcast_ip, mcast_port) VALUES (:id, 'lane1', '226.226.226.112', 112)"
        ), {"id": camera_id.hex})
        conn.execute(text(
            "INSERT INTO sessions (id, name, status, started_at) "
            "VALUES (:id, 'Range 1', 'active', CURRENT_TIMESTAMP)"
        ), {"id": session_id.hex})
        conn.execute(text(
            "INSERT INTO bullet_holes (id, session_id, camera_alias, first_seen_at, position_x, position_y, source, rank) "
            "VALUES (:id, :session, 'lane1', CURRENT_TIMESTAMP, 700, 560, 'model', 1)"
        ), {"id": hole_id.hex, "session": session_id.hex})

    with DBSession(engine) as db:
        camera_svc.delete_camera(camera_id, db)

    with engine.connect() as conn:
        sessions = conn.execute(text("SELECT id FROM sessions WHERE id = :id"), {"id": session_id.hex}).all()
        alias = conn.execute(text("SELECT camera_alias FROM bullet_holes WHERE id = :id"), {"id": hole_id.hex}).scalar()
    engine.dispose()
    assert sessions == [(session_id.hex,)]   # the Session stays, unchanged
    assert alias == "lane1"                  # its hole keeps the board it recorded


def test_the_database_holds_one_active_session_at_a_time(db_url):
    engine = _make_engine(db_url)
    insert = text("INSERT INTO sessions (id, name, status, started_at) "
                  "VALUES (:id, :name, :status, CURRENT_TIMESTAMP)")
    with engine.begin() as conn:
        conn.execute(insert, {"id": uuid.uuid4().hex, "name": "Range A", "status": "active"})
        conn.execute(insert, {"id": uuid.uuid4().hex, "name": "Old", "status": "completed"})
        conn.execute(insert, {"id": uuid.uuid4().hex, "name": "Older", "status": "completed"})
    # SQLite names the partial index violation by its column; Postgres by the index
    with pytest.raises(IntegrityError, match=r"sessions\.status|uq_sessions_one_active"), engine.begin() as conn:
        conn.execute(insert, {"id": uuid.uuid4().hex, "name": "Range B", "status": "active"})
    engine.dispose()


def test_two_starts_at_once_answer_the_second_one_409(db_url, monkeypatch):
    """Both pass the service's check before either commits: the database
    refuses the second, answered as the check would have."""
    engine = _make_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sessions (id, name, status, started_at) "
                          "VALUES (:id, 'Range A', 'active', CURRENT_TIMESTAMP)"), {"id": uuid.uuid4().hex})
    list_active = sessions_repo.list_active
    stale = [[]]   # the first check's answer, as it read just before Range A committed
    monkeypatch.setattr(sessions_repo, "list_active", lambda db: stale.pop() if stale else list_active(db))

    with DBSession(engine) as db, pytest.raises(HTTPException) as refused:
        sessions_svc.create_session(SessionCreate(name="Range B"), db)
    engine.dispose()
    assert (refused.value.status_code, refused.value.detail) == (409, "Session 'Range A' is still active: complete it first")


def test_a_start_refused_by_the_database_after_the_other_completed_is_answered_409(db_url, monkeypatch):
    """The database refused it while Range A was active, but Range A completed
    before the refusal was explained: still a 409, not a 500."""
    engine = _make_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sessions (id, name, status, started_at) "
                          "VALUES (:id, 'Range A', 'active', CURRENT_TIMESTAMP)"), {"id": uuid.uuid4().hex})
    stale = [[], []]   # both checks read no other active Session
    monkeypatch.setattr(sessions_repo, "list_active", lambda db: stale.pop())

    with DBSession(engine) as db, pytest.raises(HTTPException) as refused:
        sessions_svc.create_session(SessionCreate(name="Range B"), db)
    engine.dispose()
    assert (refused.value.status_code, refused.value.detail) == (409, "Another Session was active: try again")


def test_a_reopen_racing_a_start_is_answered_409(db_url, monkeypatch):
    engine = _make_engine(db_url)
    old = uuid.uuid4()
    insert = text("INSERT INTO sessions (id, name, status, started_at) VALUES (:id, :name, :status, CURRENT_TIMESTAMP)")
    with engine.begin() as conn:
        conn.execute(insert, {"id": uuid.uuid4().hex, "name": "Range A", "status": "active"})
        conn.execute(insert, {"id": old.hex, "name": "Old", "status": "completed"})
    list_active = sessions_repo.list_active
    stale = [[]]
    monkeypatch.setattr(sessions_repo, "list_active", lambda db: stale.pop() if stale else list_active(db))

    # Not flushed before the commit, as the app's sessions (core/database.py)
    with DBSession(engine, autoflush=False) as db, pytest.raises(HTTPException) as refused:
        sessions_svc.update_session(old, SessionUpdate(status="active"), db)
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM sessions WHERE id = :id"), {"id": old.hex}).scalar()
    engine.dispose()
    assert (refused.value.status_code, refused.value.detail) == (409, "Session 'Range A' is still active: complete it first")
    assert status == "completed"


def test_two_cameras_cannot_differ_only_in_case(db_url):
    # Windows sees Cam1 and cam1 as one recordings folder
    engine = _make_engine(db_url)
    insert = text("INSERT INTO cameras (id, alias, mcast_ip, mcast_port) VALUES (:id, :alias, '226.226.226.112', 112)")
    with engine.begin() as conn:
        conn.execute(insert, {"id": uuid.uuid4().hex, "alias": "Cam1"})
    with pytest.raises(IntegrityError, match="uq_cameras_alias_ci"), engine.begin() as conn:
        conn.execute(insert, {"id": uuid.uuid4().hex, "alias": "cam1"})
    engine.dispose()
