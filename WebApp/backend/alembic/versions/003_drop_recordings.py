"""drop the recordings feature

The WebApp no longer records or replays video, so the `recording_intervals`
table (when each Session was recording) and the `sessions.record` flag are
dropped.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite has no DROP COLUMN, so dropping sessions.record rebuilds the table.
    # Its children (bullet_holes, runs) are ON DELETE CASCADE, so dropping the
    # table they hang off would delete their rows: foreign keys off while it is
    # rebuilt keeps them. The app's engine runs this non-transactionally, so the
    # PRAGMA takes effect (SQLite ignores it inside a transaction).
    op.execute("PRAGMA foreign_keys=OFF")

    # When each Session was recording: gone with the feature
    op.drop_table("recording_intervals")

    # The operator no longer turns recording on or off
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("record")

    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")

    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("record", sa.Boolean(), nullable=False, server_default="0"))

    op.create_table(
        "recording_intervals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recording_intervals_session_id", "recording_intervals", ["session_id"])
    op.create_index(
        "uq_recording_intervals_one_open", "recording_intervals", ["session_id"], unique=True,
        sqlite_where=sa.text("ended_at IS NULL"), postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.execute("PRAGMA foreign_keys=ON")
