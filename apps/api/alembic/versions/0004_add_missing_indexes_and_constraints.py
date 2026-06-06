"""Add missing indexes and constraints absent from 0001

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-06

0001 captured the baseline tables but omitted several indexes that dev_seed.py
creates (v2, v3, v4) and a missing DEFAULT on evidence_artifacts.artifact_id.
This migration adds them idempotently.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── session_reports indexes (dev_seed v2) ─────────────────────────────────
    op.execute("CREATE INDEX IF NOT EXISTS idx_session_reports_status ON session_reports(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_session_reports_created ON session_reports(created_at)")

    # ── investigation_state indexes + auto-update trigger (dev_seed v3) ───────
    op.execute("CREATE INDEX IF NOT EXISTS idx_inv_state_status ON investigation_state(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_inv_state_expires ON investigation_state(expires_at)")

    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        DROP TRIGGER IF EXISTS update_investigation_state_updated_at ON investigation_state
    """)
    op.execute("""
        CREATE TRIGGER update_investigation_state_updated_at
            BEFORE UPDATE ON investigation_state
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column()
    """)

    # ── user / auth indexes (dev_seed v4) ────────────────────────────────────
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource_type, resource_id)")

    # ── chain_of_custody additional indexes (dev_seed v5) ────────────────────
    op.execute("CREATE INDEX IF NOT EXISTS idx_coc_agent ON chain_of_custody(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_coc_timestamp ON chain_of_custody(timestamp_utc)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_coc_entry_type ON chain_of_custody(entry_type)")

    # ── evidence_artifacts: missing DEFAULT + additional indexes ──────────────
    # Add server-side UUID default so callers don't need to supply artifact_id.
    op.execute("""
        ALTER TABLE evidence_artifacts
            ALTER COLUMN artifact_id SET DEFAULT gen_random_uuid()
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ev_root ON evidence_artifacts(root_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ev_session ON evidence_artifacts(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ev_parent ON evidence_artifacts(parent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ev_type ON evidence_artifacts(artifact_type)")

    # ── pipeline_traces: add DEFAULT to trace_id for consistency ─────────────
    # (Alembic 0002 and dev_seed v7 both omit this; trace_id is always supplied
    # by PipelineTrace.__init__ via uuid4(), so no data risk — this is cosmetic.)
    op.execute("""
        ALTER TABLE pipeline_traces
            ALTER COLUMN trace_id SET DEFAULT gen_random_uuid()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS update_investigation_state_updated_at ON investigation_state")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    op.execute("ALTER TABLE evidence_artifacts ALTER COLUMN artifact_id DROP DEFAULT")
    op.execute("ALTER TABLE pipeline_traces ALTER COLUMN trace_id DROP DEFAULT")
    # Indexes are non-destructive; leave them on downgrade to avoid data-access regression.
