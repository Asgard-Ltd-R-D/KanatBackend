"""Add each Run's kept places and watched_until (ADR-0009)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("places", postgresql.JSONB(), nullable=True))
    op.add_column("runs", sa.Column("watched_until", sa.DateTime(timezone=True), nullable=True))
    # A Run stored before them: placed where its baseline frame showed the
    # Board, and watched until that frame, all that is known of it
    op.execute(
        "UPDATE runs SET watched_until = taken_at, places = jsonb_build_array(jsonb_build_object("
        "'at', baseline_view->'taken_at', 'template_to_picture', baseline_view->'template_to_picture'))"
    )
    op.alter_column("runs", "places", nullable=False)
    op.alter_column("runs", "watched_until", nullable=False)


def downgrade() -> None:
    op.drop_column("runs", "watched_until")
    op.drop_column("runs", "places")
