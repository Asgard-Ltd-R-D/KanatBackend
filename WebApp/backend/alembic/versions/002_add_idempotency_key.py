"""Add idempotency_key to bullet_holes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bullet_holes", sa.Column("idempotency_key", sa.String(), nullable=True))
    op.create_index(
        "uq_bullet_holes_idempotency_key",
        "bullet_holes",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_bullet_holes_idempotency_key", table_name="bullet_holes")
    op.drop_column("bullet_holes", "idempotency_key")
