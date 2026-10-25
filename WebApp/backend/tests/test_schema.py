"""The schema on a real PostgreSQL: the migrations, and the rules only the
database keeps. Skipped unless TEST_DATABASE_URL names a server's database to
connect to; each test makes a database of its own there and drops it after."""
import json
import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from alembic import command
from app.config.settings import settings
from app.repositories import sessions as sessions_repo
from app.schemas.session import SessionCreate, SessionUpdate
from app.services import cameras as camera_svc
from app.services import sessions as sessions_svc

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

BEFORE_CAMERA_ID = "e5f6a7b8c9d0"
BEFORE_RUNS = "f6a7b8c9d0e1"
BEFORE_PLACES = "a7b8c9d0e1f2"
BEFORE_ONE_ACTIVE = "b8c9d0e1f2a3"


@pytest.fixture
def db_url(monkeypatch):
    """A new, empty database's URL, which alembic's env.py reads from settings."""
    name = f"kanat_test_{uuid.uuid4().hex[:12]}"
    server = create_engine(URL, isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(URL).set(database=name).render_as_string(hide_password=False)
    monkeypatch.setattr(settings, "database_url", url)
    try:
        yield url
    finally:
        with server.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        server.dispose()


def alembic_config():
    # No config file name, so env.py leaves the test run's logging alone
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    return config


def schema(url):
    """The sessions table's columns, and whether the runs table exists."""
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        return {c["name"] for c in inspector.get_columns("sessions")}, inspector.has_table("runs")
    finally:
        engine.dispose()


def test_the_migrations_apply_and_reverse_cleanly(db_url):
    config = alembic_config()

    command.upgrade(config, "head")
    columns, runs = schema(db_url)
    assert "camera_id" in columns and runs
    command.downgrade(config, BEFORE_RUNS)
    columns, runs = schema(db_url)
    assert "camera_id" in columns and not runs
    command.downgrade(config, BEFORE_CAMERA_ID)
    assert "camera_id" not in schema(db_url)[0]
    command.upgrade(config, "head")
    columns, runs = schema(db_url)
    assert "camera_id" in columns and runs


def test_deleting_a_camera_clears_it_on_its_sessions(db_url):
    command.upgrade(alembic_config(), "head")
    engine = create_engine(db_url)
    camera_id, session_id = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cameras (id, alias, mcast_ip, mcast_port) VALUES (:id, 'cam1', '226.226.226.112', 112)"
        ), {"id": camera_id})
        conn.execute(text(
            "INSERT INTO sessions (id, name, status, started_at, camera_id) VALUES (:id, 'Range 1', 'active', now(), :camera)"
        ), {"id": session_id, "camera": camera_id})

    with DBSession(engine) as db:
        camera_svc.delete_camera(camera_id, db)

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT camera_id FROM sessions WHERE id = :id"), {"id": session_id}).all()
    engine.dispose()
    assert rows == [(None,)]   # the Session stays, without its camera


def test_a_run_stored_before_its_places_is_placed_and_watched_as_its_baseline(db_url):
    """Places and watched_until apply and reverse cleanly; a Run stored
    before them keeps the place its baseline frame showed the Board at, and
    reads watched until then."""
    config = alembic_config()
    command.upgrade(config, BEFORE_PLACES)
    engine = create_engine(db_url)
    session_id = uuid.uuid4()
    H = [[0.25, 0.0, 600.0], [0.0, 0.25, 300.0], [0.0, 0.0, 1.0]]
    view = {"taken_at": "2026-10-22T10:15:02.120000Z", "picture": {"width": 1920, "height": 1080},
            "template_to_picture": H, "targets": [], "baseline_marks": []}
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO sessions (id, name, status, started_at) VALUES (:id, 'Range 1', 'active', now())"
        ), {"id": session_id})
        conn.execute(text(
            "INSERT INTO runs (id, session_id, camera_alias, taken_at, baseline_view) "
            "VALUES (:id, :session, 'lane1', '2026-10-22T10:15:02.120Z', CAST(:view AS jsonb))"
        ), {"id": uuid.uuid4(), "session": session_id, "view": json.dumps(view)})

    command.upgrade(config, "head")
    with engine.connect() as conn:
        places, watched_until, taken_at = conn.execute(
            text("SELECT places, watched_until, taken_at FROM runs")).one()
    assert places == [{"at": view["taken_at"], "template_to_picture": H}]
    assert watched_until == taken_at

    command.downgrade(config, BEFORE_PLACES)
    columns = {c["name"] for c in inspect(engine).get_columns("runs")}
    engine.dispose()
    assert not {"places", "watched_until"} & columns


def test_the_database_holds_one_active_session_at_a_time(db_url):
    command.upgrade(alembic_config(), "head")
    engine = create_engine(db_url)
    insert = text("INSERT INTO sessions (id, name, status, started_at) VALUES (:id, :name, :status, now())")
    with engine.begin() as conn:
        conn.execute(insert, {"id": uuid.uuid4(), "name": "Range A", "status": "active"})
        conn.execute(insert, {"id": uuid.uuid4(), "name": "Old", "status": "completed"})
        conn.execute(insert, {"id": uuid.uuid4(), "name": "Older", "status": "completed"})
    with pytest.raises(IntegrityError, match="uq_sessions_one_active"), engine.begin() as conn:
        conn.execute(insert, {"id": uuid.uuid4(), "name": "Range B", "status": "active"})
    engine.dispose()


def test_two_starts_at_once_answer_the_second_one_409(db_url, monkeypatch):
    """Both pass the service's check before either commits: the database
    refuses the second, answered as the check would have."""
    command.upgrade(alembic_config(), "head")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sessions (id, name, status, started_at) "
                          "VALUES (:id, 'Range A', 'active', now())"), {"id": uuid.uuid4()})
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
    command.upgrade(alembic_config(), "head")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sessions (id, name, status, started_at) "
                          "VALUES (:id, 'Range A', 'active', now())"), {"id": uuid.uuid4()})
    stale = [[], []]   # both checks read no other active Session
    monkeypatch.setattr(sessions_repo, "list_active", lambda db: stale.pop())

    with DBSession(engine) as db, pytest.raises(HTTPException) as refused:
        sessions_svc.create_session(SessionCreate(name="Range B"), db)
    engine.dispose()
    assert (refused.value.status_code, refused.value.detail) == (409, "Another Session was active: try again")


def test_a_reopen_racing_a_start_is_answered_409(db_url, monkeypatch):
    command.upgrade(alembic_config(), "head")
    engine = create_engine(db_url)
    old = uuid.uuid4()
    insert = text("INSERT INTO sessions (id, name, status, started_at) VALUES (:id, :name, :status, now())")
    with engine.begin() as conn:
        conn.execute(insert, {"id": uuid.uuid4(), "name": "Range A", "status": "active"})
        conn.execute(insert, {"id": old, "name": "Old", "status": "completed"})
    list_active = sessions_repo.list_active
    stale = [[]]
    monkeypatch.setattr(sessions_repo, "list_active", lambda db: stale.pop() if stale else list_active(db))

    # Not flushed before the commit, as the app's sessions (core/database.py)
    with DBSession(engine, autoflush=False) as db, pytest.raises(HTTPException) as refused:
        sessions_svc.update_session(old, SessionUpdate(status="active"), db)
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM sessions WHERE id = :id"), {"id": old}).scalar()
    engine.dispose()
    assert (refused.value.status_code, refused.value.detail) == (409, "Session 'Range A' is still active: complete it first")
    assert status == "completed"


def test_the_one_active_session_migration_refuses_several_active_naming_them(db_url):
    config = alembic_config()
    command.upgrade(config, BEFORE_ONE_ACTIVE)
    engine = create_engine(db_url)
    insert = text("INSERT INTO sessions (id, name, status, started_at) "
                  "VALUES (:id, :name, 'active', now() - make_interval(mins => :ago))")
    with engine.begin() as conn:
        conn.execute(insert, {"id": uuid.uuid4(), "name": "Range A", "ago": 10})
        conn.execute(insert, {"id": uuid.uuid4(), "name": "Range B", "ago": 5})

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO recording_intervals (id, session_id, started_at) "
                          "SELECT gen_random_uuid(), id, now() FROM sessions"))

    with pytest.raises(RuntimeError, match=r"2 Sessions are active \(Range A, Range B\)") as refused:
        command.upgrade(config, "head")
    # The command it names completes all but the latest, as the app would
    sql = str(refused.value).split('-c "')[1].split('"\n')[0]
    with engine.begin() as conn:
        conn.execute(text(sql))
        left = conn.execute(text("SELECT s.name, s.status, s.ended_at IS NULL, i.ended_at IS NULL FROM sessions s "
                                 "JOIN recording_intervals i ON i.session_id = s.id ORDER BY s.name")).all()
    assert left == [("Range A", "completed", False, False), ("Range B", "active", True, True)]
    command.upgrade(config, "head")
    command.downgrade(config, BEFORE_ONE_ACTIVE)
    indexes = {i["name"] for i in inspect(engine).get_indexes("sessions")}
    engine.dispose()
    assert "uq_sessions_one_active" not in indexes
