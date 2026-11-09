from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config.settings import settings


def _make_engine(url: str):
    """The database engine. SQLite needs a few connection settings the backend
    relies on and Postgres gives for free:
    - check_same_thread off: the backend shares the engine across the request
      threadpool and the camera_sync/detection_sync background loops;
    - foreign_keys ON: SQLite ignores FK actions (ON DELETE CASCADE / SET NULL)
      otherwise, so deleting a Session would orphan its bullets, intervals and runs;
    - WAL and a busy timeout: a reader does not block the single writer, and a
      write waits briefly for a lock instead of failing at once."""
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        return eng
    return create_engine(url)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
