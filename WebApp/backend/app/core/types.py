"""Shared SQLAlchemy column types."""
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """A timezone-aware UTC datetime that survives SQLite.

    Postgres has a timezone-aware timestamp; SQLite stores datetimes as naive
    text and drops the tzinfo, so a value written aware comes back naive and the
    app's comparisons raise "can't compare offset-naive and offset-aware". This
    normalises every value to UTC on the way in and re-attaches UTC on the way
    out, so columns stay aware UTC on either database. A naive value is assumed
    to already be UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
