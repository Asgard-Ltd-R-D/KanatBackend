"""store a baseline frame image per Run

`runs.baseline_image_path` is where the captured baseline camera frame of a
Run is kept, relative to the log directory. Null until one is uploaded.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("baseline_image_path", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("baseline_image_path")
