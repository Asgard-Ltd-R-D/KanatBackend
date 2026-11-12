"""sessions span all cameras

A Session no longer watches one chosen camera; it spans every enabled camera,
one board each. So each Bullet Hole gains the board it is on (its camera's
alias), the single `sessions.camera_id` is dropped, and a Run is told apart by
its camera as well as its baseline time (two boards can take a baseline at the
same instant).

The hole's board is backfilled from its Session's old camera before the column
is dropped, so a Session that watched one camera keeps reading as a one-board
Session.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite has no DROP COLUMN, so dropping sessions.camera_id rebuilds the
    # table (copy, drop old, rename). The old sessions table's children
    # (bullet_holes, runs) are ON DELETE CASCADE, so dropping it would delete
    # their rows: foreign keys off while the tables are rebuilt keeps them.
    # The app's engine runs this non-transactionally, so the PRAGMA takes
    # effect (SQLite ignores it inside a transaction).
    op.execute("PRAGMA foreign_keys=OFF")

    # Each Bullet Hole's board, named by its camera's alias
    with op.batch_alter_table("bullet_holes") as batch:
        batch.add_column(sa.Column("camera_alias", sa.String(), nullable=True))
    # Backfill from the Session's old camera, while sessions.camera_id still
    # exists: a hole of a Session that watched a camera gets that camera's alias.
    # A camera deleted before this upgrade left sessions.camera_id NULL, so the
    # join finds nothing; its alias is still on the Session's saved runs (one
    # camera a Session then, so one alias), so fall back to those, keeping those
    # holes on their board in replay instead of dropping them to "no board".
    op.execute(
        """
        UPDATE bullet_holes
        SET camera_alias = COALESCE(
            (SELECT c.alias FROM sessions s JOIN cameras c ON c.id = s.camera_id
             WHERE s.id = bullet_holes.session_id),
            (SELECT r.camera_alias FROM runs r
             WHERE r.session_id = bullet_holes.session_id AND r.camera_alias IS NOT NULL
             LIMIT 1)
        )
        """
    )

    # The single chosen camera is gone: a Session spans every enabled camera
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("camera_id")

    # A Run's identity now includes its camera
    with op.batch_alter_table("runs") as batch:
        batch.drop_constraint("uq_runs_session_id_taken_at", type_="unique")
        batch.create_unique_constraint(
            "uq_runs_session_id_camera_alias_taken_at", ["session_id", "camera_alias", "taken_at"]
        )

    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("runs") as batch:
        batch.drop_constraint("uq_runs_session_id_camera_alias_taken_at", type_="unique")
        batch.create_unique_constraint("uq_runs_session_id_taken_at", ["session_id", "taken_at"])

    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("camera_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_sessions_camera_id_cameras", "cameras", ["camera_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("bullet_holes") as batch:
        batch.drop_column("camera_alias")

    op.execute("PRAGMA foreign_keys=ON")
