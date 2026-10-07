"""Initial schema: sessions and bullet_holes

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-10-06 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "bullet_holes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=False),
        sa.Column("position_y", sa.Float(), nullable=False),
        sa.Column("target_index", sa.Integer(), nullable=True),
        sa.Column("x_mm", sa.Float(), nullable=True),
        sa.Column("y_mm", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="model"),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_bullet_holes_session_id", "bullet_holes", ["session_id"])
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_bullet_holes_session_id", table_name="bullet_holes")
    op.drop_index("ix_sessions_created_at", table_name="sessions")
    op.drop_table("bullet_holes")
    op.drop_table("sessions")
