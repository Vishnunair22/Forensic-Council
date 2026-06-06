"""Add forensic core tables missing from Alembic baseline

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-06

Five tables exist only in dev_seed.py v5 and are absent from all Alembic
migrations. Without this migration, a database bootstrapped exclusively
via `alembic upgrade head` would be missing hitl_checkpoints, forensic_reports,
calibration_models, inter_agent_calls, and tribunal_cases — causing runtime
failures on any code path that touches those tables.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.execute("""
        CREATE TABLE IF NOT EXISTS calibration_models (
            model_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id          VARCHAR(64) NOT NULL,
            method            VARCHAR(64) NOT NULL,
            benchmark_dataset VARCHAR(255) NOT NULL,
            version           VARCHAR(64) NOT NULL,
            created_utc       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            params            JSONB NOT NULL,
            UNIQUE(agent_id, version)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cal_agent ON calibration_models(agent_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS hitl_checkpoints (
            checkpoint_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id            VARCHAR(64) NOT NULL,
            session_id          UUID NOT NULL,
            reason              VARCHAR(64) NOT NULL,
            current_finding     JSONB,
            paused_at_iteration INTEGER NOT NULL,
            investigator_brief  TEXT,
            status              VARCHAR(64) NOT NULL DEFAULT 'PAUSED',
            serialized_state    JSONB NOT NULL,
            created_utc         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_utc        TIMESTAMPTZ,
            human_decision      JSONB
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_hitl_session ON hitl_checkpoints(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_checkpoints(status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS inter_agent_calls (
            call_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            caller_agent_id VARCHAR(64) NOT NULL,
            callee_agent_id VARCHAR(64) NOT NULL,
            call_type       VARCHAR(64) NOT NULL,
            payload         JSONB NOT NULL,
            response        JSONB,
            status          VARCHAR(64) NOT NULL DEFAULT 'PENDING',
            created_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_utc   TIMESTAMPTZ,
            session_id      UUID NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_iac_session ON inter_agent_calls(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_iac_caller ON inter_agent_calls(caller_agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_iac_callee ON inter_agent_calls(callee_agent_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS tribunal_cases (
            tribunal_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id     UUID NOT NULL,
            agent_a_id     VARCHAR(64) NOT NULL,
            agent_b_id     VARCHAR(64) NOT NULL,
            contradiction  JSONB NOT NULL,
            human_judgment JSONB,
            resolved       BOOLEAN NOT NULL DEFAULT FALSE,
            created_utc    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_utc   TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tribunal_session ON tribunal_cases(session_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS forensic_reports (
            report_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id             UUID NOT NULL UNIQUE,
            case_id                VARCHAR(255) NOT NULL,
            executive_summary      TEXT NOT NULL,
            per_agent_findings     JSONB NOT NULL,
            cross_modal_confirmed  JSONB NOT NULL DEFAULT '[]',
            contested_findings     JSONB NOT NULL DEFAULT '[]',
            tribunal_resolved      JSONB NOT NULL DEFAULT '[]',
            incomplete_findings    JSONB NOT NULL DEFAULT '[]',
            case_linking_flags     JSONB NOT NULL DEFAULT '[]',
            chain_of_custody_log   JSONB NOT NULL DEFAULT '[]',
            evidence_version_trees JSONB NOT NULL DEFAULT '[]',
            react_chains           JSONB NOT NULL DEFAULT '{}',
            self_reflection_outputs JSONB NOT NULL DEFAULT '{}',
            uncertainty_statement  TEXT NOT NULL,
            cryptographic_signature TEXT NOT NULL,
            report_hash            VARCHAR(64) NOT NULL,
            signed_utc             TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_reports_session ON forensic_reports(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reports_case ON forensic_reports(case_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS forensic_reports CASCADE")
    op.execute("DROP TABLE IF EXISTS tribunal_cases CASCADE")
    op.execute("DROP TABLE IF EXISTS inter_agent_calls CASCADE")
    op.execute("DROP TABLE IF EXISTS hitl_checkpoints CASCADE")
    op.execute("DROP TABLE IF EXISTS calibration_models CASCADE")
