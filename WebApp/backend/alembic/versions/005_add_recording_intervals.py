"""Add recording_intervals, the stretches of each session with recording on

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recording_intervals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recording_intervals_session_id", "recording_intervals", ["session_id"])
    # A session records in one interval at a time: a second open one would be
    # left open for good, and keep the cameras recording
    op.create_index(
        "uq_recording_intervals_one_open",
        "recording_intervals",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    # A session recording before this table: one interval over its whole time,
    # as recording was then switched for the whole session
    op.execute(
        "INSERT INTO recording_intervals (id, session_id, started_at, ended_at) "
        "SELECT gen_random_uuid(), id, started_at, ended_at FROM sessions WHERE record"
    )


def downgrade() -> None:
    op.drop_index("uq_recording_intervals_one_open", table_name="recording_intervals")
    op.drop_index("ix_recording_intervals_session_id", table_name="recording_intervals")
    op.drop_table("recording_intervals")
