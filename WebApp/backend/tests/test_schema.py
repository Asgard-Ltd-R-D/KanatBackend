"""The schema on a real PostgreSQL: the migrations, and the rules only the
database keeps. Skipped unless TEST_DATABASE_URL names a server's database to
connect to; each test makes a database of its own there and drops it after."""
import json
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as DBSession

from app.config.settings import settings
from app.services import cameras as camera_svc

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

BEFORE_CAMERA_ID = "e5f6a7b8c9d0"
BEFORE_RUNS = "f6a7b8c9d0e1"
BEFORE_PLACES = "a7b8c9d0e1f2"


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
