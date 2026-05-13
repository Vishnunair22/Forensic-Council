"""Initial forensic council schema

Revision ID: 0001
Revises:
Create Date: 2026-05-09

Captures the existing schema from scripts/init_db.py as Alembic baseline.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0. Enable UUID extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # 1. users table
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(64) PRIMARY KEY,
            username VARCHAR(255) NOT NULL UNIQUE,
            email VARCHAR(255) UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            role VARCHAR(64) NOT NULL DEFAULT 'investigator',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_disabled BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}'
        )
    """)

    # 2. session_reports table
    op.execute("""
        CREATE TABLE IF NOT EXISTS session_reports (
            session_id UUID PRIMARY KEY,
            case_id VARCHAR(255) NOT NULL,
            investigator_id VARCHAR(255) NOT NULL,
            status VARCHAR(64) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            report_data JSONB,
            error_message TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'
        )
    """)

    # 3. investigation_state table
    op.execute("""
        CREATE TABLE IF NOT EXISTS investigation_state (
            session_id UUID PRIMARY KEY,
            case_id VARCHAR(255) NOT NULL,
            investigator_id VARCHAR(255) NOT NULL,
            pipeline_state JSONB NOT NULL,
            agent_results JSONB NOT NULL DEFAULT '{}',
            checkpoints JSONB NOT NULL DEFAULT '[]',
            status VARCHAR(64) NOT NULL DEFAULT 'running',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours')
        )
    """)

    # 4. user_sessions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_token VARCHAR(255) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            ip_address INET,
            user_agent TEXT
        )
    """)

    # 5. audit_log table
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(64) REFERENCES users(user_id),
            action VARCHAR(255) NOT NULL,
            resource_type VARCHAR(128) NOT NULL,
            resource_id VARCHAR(255),
            details JSONB NOT NULL DEFAULT '{}',
            ip_address INET,
            user_agent TEXT,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # 6. chain_of_custody table
    op.execute("""
        CREATE TABLE IF NOT EXISTS chain_of_custody (
            entry_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entry_type      VARCHAR(64) NOT NULL,
            agent_id        VARCHAR(64) NOT NULL,
            session_id      UUID NOT NULL,
            timestamp_utc   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            content         JSONB NOT NULL,
            content_hash    VARCHAR(64) NOT NULL,
            signature       TEXT NOT NULL,
            prior_entry_ref VARCHAR(64)
        )
    """)

    # 7. evidence_artifacts table
    op.execute("""
        CREATE TABLE IF NOT EXISTS evidence_artifacts (
            artifact_id   UUID PRIMARY KEY,
            parent_id     UUID REFERENCES evidence_artifacts(artifact_id),
            root_id       UUID NOT NULL,
            artifact_type VARCHAR(64) NOT NULL,
            file_path     TEXT NOT NULL,
            content_hash  VARCHAR(64) NOT NULL,
            action        TEXT NOT NULL,
            agent_id      VARCHAR(64) NOT NULL,
            session_id    UUID NOT NULL,
            timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata      JSONB NOT NULL DEFAULT '{}'
        )
    """)

    # Indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_session_reports_case ON session_reports(case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_coc_session ON chain_of_custody(session_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evidence_artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS chain_of_custody CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS user_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS investigation_state CASCADE")
    op.execute("DROP TABLE IF EXISTS session_reports CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
