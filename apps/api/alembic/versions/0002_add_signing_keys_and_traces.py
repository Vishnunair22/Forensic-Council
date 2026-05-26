"""Add agent_signing_keys and pipeline_traces tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-26

These two tables exist in core/migrations.py (versions 6 and 7) but were
absent from the initial Alembic baseline. Alembic is the canonical migration
authority; core/migrations.py is retained only as a dev-mode fallback seeder.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 8. agent_signing_keys — per-agent ECDSA P-256 key pairs (encrypted at rest via Fernet)
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_signing_keys (
            key_id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id                  VARCHAR(64) NOT NULL,
            encrypted_private_key_pem TEXT NOT NULL,
            public_key_pem            TEXT NOT NULL,
            is_active                 BOOLEAN NOT NULL DEFAULT TRUE,
            created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            retired_at                TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ask_agent_active
            ON agent_signing_keys(agent_id) WHERE is_active = true
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ask_agent ON agent_signing_keys(agent_id)")

    # 9. pipeline_traces — forensic hierarchical pipeline audit trail
    op.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_traces (
            trace_id       UUID PRIMARY KEY,
            parent_id      UUID,
            session_id     UUID NOT NULL,
            agent_id       VARCHAR(64) NOT NULL,
            operation      VARCHAR(255) NOT NULL,
            status         VARCHAR(64) NOT NULL,
            metadata       JSONB NOT NULL DEFAULT '{}',
            start_time_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            end_time_utc   TIMESTAMPTZ,
            duration_ms    INTEGER
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_traces_session ON pipeline_traces(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_traces_parent ON pipeline_traces(parent_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pipeline_traces CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_traces_parent")
    op.execute("DROP INDEX IF EXISTS idx_traces_session")
    op.execute("DROP TABLE IF EXISTS agent_signing_keys CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_ask_agent")
    op.execute("DROP INDEX IF EXISTS idx_ask_agent_active")
