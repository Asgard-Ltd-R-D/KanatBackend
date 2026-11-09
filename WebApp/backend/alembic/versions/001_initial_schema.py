"""initial schema

The whole WebApp schema in one migration, for SQLite (and kept
dialect-agnostic, so it also runs on Postgres). It replaces the earlier chain of
ten migrations: there is no deployed data to preserve, so the history was
collapsed when the database moved from Postgres to SQLite.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-11-08
"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cameras",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("mcast_ip", sa.String(), nullable=False),
        sa.Column("mcast_port", sa.Integer(), nullable=False),
        sa.Column("iface", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique whatever the case: the alias names the camera's recordings folder,
    # and Windows sees Cam1 and cam1 as one folder
    op.create_index("uq_cameras_alias_ci", "cameras", [sa.text("lower(alias)")], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("camera_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("status IN ('active', 'completed')", name="ck_sessions_status"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"])
    # One active Session at a time (services/sessions.py checks it first)
    op.create_index(
        "uq_sessions_one_active", "sessions", ["status"], unique=True,
        sqlite_where=sa.text("status = 'active'"), postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "bullet_holes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=False),
        sa.Column("position_y", sa.Float(), nullable=False),
        sa.Column("target_index", sa.Integer(), nullable=True),
        sa.Column("x_mm", sa.Float(), nullable=True),
        sa.Column("y_mm", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bullet_holes_session_id", "bullet_holes", ["session_id"])
    # Many NULL keys (manual bullets), unique only when a key is present
    op.create_index(
        "uq_bullet_holes_session_idempotency_key", "bullet_holes", ["session_id", "idempotency_key"], unique=True,
        sqlite_where=sa.text("idempotency_key IS NOT NULL"), postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

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
    # One open interval per session at most
    op.create_index(
        "uq_recording_intervals_one_open", "recording_intervals", ["session_id"], unique=True,
        sqlite_where=sa.text("ended_at IS NULL"), postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("camera_alias", sa.String(), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_view", sa.JSON(), nullable=False),
        sa.Column("places", sa.JSON(), nullable=False),
        sa.Column("watched_until", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "taken_at", name="uq_runs_session_id_taken_at"),
    )


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_index("uq_recording_intervals_one_open", table_name="recording_intervals")
    op.drop_index("ix_recording_intervals_session_id", table_name="recording_intervals")
    op.drop_table("recording_intervals")
    op.drop_index("uq_bullet_holes_session_idempotency_key", table_name="bullet_holes")
    op.drop_index("ix_bullet_holes_session_id", table_name="bullet_holes")
    op.drop_table("bullet_holes")
    op.drop_index("uq_sessions_one_active", table_name="sessions")
    op.drop_index("ix_sessions_created_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("uq_cameras_alias_ci", table_name="cameras")
    op.drop_table("cameras")
