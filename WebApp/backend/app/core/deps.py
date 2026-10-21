from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def short_db() -> Iterator[Session]:
    """A session of its own for one quick query, for a request that released
    its own before a long wait (e.g. a replay download), so no connection is
    held meanwhile."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
