#!/usr/bin/env python3
"""
Database Initialization Script
==============================

Creates the PostgreSQL schema for the Forensic Council system.
Run this script after starting the PostgreSQL container.

Usage:
    python scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import get_settings
from core.logging import get_logger, configure_root_logger
from infra.postgres_client import PostgresClient

logger = get_logger(__name__)


# SQL statements to create the schema
SCHEMA_SQL = """
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Chain of Custody Table
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
);

-- Indexes for chain_of_custody
CREATE INDEX IF NOT EXISTS idx_coc_session ON chain_of_custody(session_id);
CREATE INDEX IF NOT EXISTS idx_coc_agent ON chain_of_custody(agent_id);
CREATE INDEX IF NOT EXISTS idx_coc_timestamp ON chain_of_custody(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_coc_entry_type ON chain_of_custody(entry_type);

-- Evidence Artifacts Table
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
);

-- Indexes for evidence_artifacts
CREATE INDEX IF NOT EXISTS idx_ev_root ON evidence_artifacts(root_id);
CREATE INDEX IF NOT EXISTS idx_ev_session ON evidence_artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_ev_parent ON evidence_artifacts(parent_id);
CREATE INDEX IF NOT EXISTS idx_ev_type ON evidence_artifacts(artifact_type);

-- Calibration Models Table (for Stage 9)
CREATE TABLE IF NOT EXISTS calibration_models (
    model_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        VARCHAR(64) NOT NULL,
    method          VARCHAR(64) NOT NULL,
    benchmark_dataset VARCHAR(255) NOT NULL,
    version         VARCHAR(64) NOT NULL,
    created_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    params          JSONB NOT NULL,
    UNIQUE(agent_id, version)
);

-- Index for calibration_models
CREATE INDEX IF NOT EXISTS idx_cal_agent ON calibration_models(agent_id);

-- HITL Checkpoints Table (for Stage 4)
CREATE TABLE IF NOT EXISTS hitl_checkpoints (
    checkpoint_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id          VARCHAR(64) NOT NULL,
    session_id        UUID NOT NULL,
    reason            VARCHAR(64) NOT NULL,
    current_finding   JSONB,
    paused_at_iteration INTEGER NOT NULL,
    investigator_brief TEXT,
    status            VARCHAR(64) NOT NULL DEFAULT 'PAUSED',
    serialized_state  JSONB NOT NULL,
    created_utc       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_utc      TIMESTAMPTZ,
    human_decision    JSONB
);

-- Indexes for hitl_checkpoints
CREATE INDEX IF NOT EXISTS idx_hitl_session ON hitl_checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_checkpoints(status);

-- Inter-Agent Calls Table (for Stage 8)
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
);

-- Indexes for inter_agent_calls
CREATE INDEX IF NOT EXISTS idx_iac_session ON inter_agent_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_iac_caller ON inter_agent_calls(caller_agent_id);
CREATE INDEX IF NOT EXISTS idx_iac_callee ON inter_agent_calls(callee_agent_id);

-- Tribunal Cases Table (for Stage 11)
CREATE TABLE IF NOT EXISTS tribunal_cases (
    tribunal_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID NOT NULL,
    agent_a_id        VARCHAR(64) NOT NULL,
    agent_b_id        VARCHAR(64) NOT NULL,
    contradiction     JSONB NOT NULL,
    human_judgment    JSONB,
    resolved          BOOLEAN NOT NULL DEFAULT FALSE,
    created_utc       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_utc      TIMESTAMPTZ
);

-- Index for tribunal_cases
CREATE INDEX IF NOT EXISTS idx_tribunal_session ON tribunal_cases(session_id);

-- Forensic Reports Table (for Stage 11)
CREATE TABLE IF NOT EXISTS forensic_reports (
    report_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL UNIQUE,
    case_id             VARCHAR(255) NOT NULL,
    executive_summary   TEXT NOT NULL,
    per_agent_findings  JSONB NOT NULL,
    cross_modal_confirmed JSONB NOT NULL DEFAULT '[]',
    contested_findings  JSONB NOT NULL DEFAULT '[]',
    tribunal_resolved   JSONB NOT NULL DEFAULT '[]',
    incomplete_findings JSONB NOT NULL DEFAULT '[]',
    case_linking_flags  JSONB NOT NULL DEFAULT '[]',
    chain_of_custody_log JSONB NOT NULL DEFAULT '[]',
    evidence_version_trees JSONB NOT NULL DEFAULT '[]',
    react_chains        JSONB NOT NULL DEFAULT '{}',
    self_reflection_outputs JSONB NOT NULL DEFAULT '{}',
    uncertainty_statement TEXT NOT NULL,
    cryptographic_signature TEXT NOT NULL,
    report_hash         VARCHAR(64) NOT NULL,
    signed_utc          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for forensic_reports
CREATE INDEX IF NOT EXISTS idx_reports_session ON forensic_reports(session_id);
CREATE INDEX IF NOT EXISTS idx_reports_case ON forensic_reports(case_id);
"""


async def init_database() -> bool:
    """
    Initialize the database schema.
    
    Returns:
        True if successful, False otherwise
    """
    configure_root_logger("INFO")
    
    settings = get_settings()
    logger.info("Connecting to database...", host=settings.postgres_host, database=settings.postgres_db)
    
    client = PostgresClient()
    
    try:
        await client.connect()
        logger.info("Connected to PostgreSQL")
        
        # Execute schema creation
        await client.execute(SCHEMA_SQL)
        logger.info("Schema created successfully")
        
        # Verify tables exist
        tables = await client.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        table_names = [t["table_name"] for t in tables]
        logger.info("Tables created", tables=table_names)
        
        expected_tables = [
            "chain_of_custody",
            "evidence_artifacts",
            "calibration_models",
            "hitl_checkpoints",
            "inter_agent_calls",
            "tribunal_cases",
            "forensic_reports",
        ]
        
        for table in expected_tables:
            if table not in table_names:
                logger.error("Missing table", table=table)
                return False
        
        logger.info("Schema initialized successfully")
        return True
        
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        return False
    finally:
        await client.disconnect()


def main():
    """Main entry point."""
    success = asyncio.run(init_database())
    
    if success:
        print("\n[OK] Schema initialized successfully")
        print("\nTables created:")
        print("  - chain_of_custody")
        print("  - evidence_artifacts")
        print("  - calibration_models")
        print("  - hitl_checkpoints")
        print("  - inter_agent_calls")
        print("  - tribunal_cases")
        print("  - forensic_reports")
        sys.exit(0)
    else:
        print("\n[ERROR] Schema initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
