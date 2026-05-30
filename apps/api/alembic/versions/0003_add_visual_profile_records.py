"""Add visual_profile_records table for persistent visual evidence profiles

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-30

Agent 1's visual evidence profile is now persisted to enable recovery
from worker restarts and to support versioned access by downstream agents
and the Arbiter.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS visual_profile_records (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id      UUID NOT NULL,
            version         INTEGER NOT NULL DEFAULT 1,
            agent_id        VARCHAR(64) NOT NULL,
            profile_data    JSONB NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (session_id, version)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_vpr_session ON visual_profile_records(session_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_vpr_session")
    op.execute("DROP TABLE IF EXISTS visual_profile_records CASCADE")
