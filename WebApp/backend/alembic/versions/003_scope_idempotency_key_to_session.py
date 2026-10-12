"""Scope idempotency_key unique index to (session_id, idempotency_key)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_bullet_holes_idempotency_key", table_name="bullet_holes")
    op.create_index(
        "uq_bullet_holes_session_idempotency_key",
        "bullet_holes",
        ["session_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_bullet_holes_session_idempotency_key", table_name="bullet_holes")
    op.create_index(
        "uq_bullet_holes_idempotency_key",
        "bullet_holes",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
