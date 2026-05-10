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
    # Users table
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'investigator',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_login TIMESTAMPTZ,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)

    # Sessions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS investigation_sessions (
            session_id UUID PRIMARY KEY,
            case_id VARCHAR(255) NOT NULL,
            investigator_id VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'queued',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            pipeline_state JSONB,
            report JSONB
        )
    """)

    # Custody log table
    op.execute("""
        CREATE TABLE IF NOT EXISTS custody_log (
            log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL,
            agent_id VARCHAR(100) NOT NULL,
            entry_type VARCHAR(50) NOT NULL,
            content JSONB NOT NULL,
            timestamp_utc TIMESTAMPTZ DEFAULT NOW(),
            signature TEXT,
            FOREIGN KEY (session_id) REFERENCES investigation_sessions(session_id) ON DELETE CASCADE
        )
    """)

    # Evidence store table
    op.execute("""
        CREATE TABLE IF NOT EXISTS evidence_artifacts (
            artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL,
            original_filename VARCHAR(500),
            mime_type VARCHAR(200),
            file_size_bytes BIGINT,
            sha256_hash VARCHAR(64),
            storage_path TEXT,
            uploaded_at TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (session_id) REFERENCES investigation_sessions(session_id) ON DELETE CASCADE
        )
    """)

    # Findings table
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_findings (
            finding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL,
            agent_id VARCHAR(100) NOT NULL,
            finding_type VARCHAR(500) NOT NULL,
            evidence_verdict VARCHAR(50) NOT NULL DEFAULT 'INCONCLUSIVE',
            confidence_raw FLOAT,
            calibration_status VARCHAR(50) DEFAULT 'UNCALIBRATED',
            status VARCHAR(50) NOT NULL DEFAULT 'CONFIRMED',
            reasoning_summary TEXT,
            metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (session_id) REFERENCES investigation_sessions(session_id) ON DELETE CASCADE
        )
    """)

    # Indexes for performance
    op.execute("CREATE INDEX IF NOT EXISTS idx_custody_log_session ON custody_log(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_custody_log_timestamp ON custody_log(timestamp_utc)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_findings_session ON agent_findings(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_findings_agent ON agent_findings(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_investigator ON investigation_sessions(investigator_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON investigation_sessions(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_findings CASCADE")
    op.execute("DROP TABLE IF EXISTS evidence_artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS custody_log CASCADE")
    op.execute("DROP TABLE IF EXISTS investigation_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
