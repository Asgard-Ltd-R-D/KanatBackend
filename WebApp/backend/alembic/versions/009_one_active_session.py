"""At most one active Session at a time

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-25 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Completes every active Session but the latest started, closing their open
# recording intervals, as the app completes one: the command the refusal names
COMPLETE_ALL_BUT_LATEST = (
    "WITH extra AS (SELECT id FROM sessions WHERE status = 'active' AND id <> "
    "(SELECT id FROM sessions WHERE status = 'active' ORDER BY started_at DESC LIMIT 1)), "
    "closed AS (UPDATE recording_intervals SET ended_at = now() "
    "WHERE ended_at IS NULL AND session_id IN (SELECT id FROM extra)) "
    "UPDATE sessions SET status = 'completed', ended_at = now() WHERE id IN (SELECT id FROM extra)"
)


def upgrade() -> None:
    # Which of several active Sessions to complete is the operator's call, not
    # a migration's: refuse, naming them, with the command that completes all
    # but the latest, as the app cannot start to do it before this has run
    active = op.get_bind().execute(
        sa.text("SELECT name FROM sessions WHERE status = 'active' ORDER BY started_at")
    ).scalars().all()
    if len(active) > 1:
        raise RuntimeError(
            f"{len(active)} Sessions are active ({', '.join(active)}): only one may be. To complete "
            f"all but the latest started ({active[-1]}), run\n"
            f'  docker exec webapp-postgres psql -U postgres -d pdb -c "{COMPLETE_ALL_BUT_LATEST}"\n'
            "then run this migration again"
        )
    # Unique on status among the active rows only: a second active row collides
    op.create_index(
        "uq_sessions_one_active", "sessions", ["status"], unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_sessions_one_active", table_name="sessions")
