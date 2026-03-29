"""
Database Migration System
=========================

Version-controlled database migrations for production deployments.
Tracks applied migrations and ensures idempotent schema updates.
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional

from infra.postgres_client import PostgresClient, get_postgres_client
from core.structured_logging import get_logger

logger = get_logger(__name__)


@dataclass
class Migration:
    """Represents a database migration."""
    version: int
    name: str
    description: str
    sql: str
    rollback_sql: Optional[str] = None


# Migration registry - add new migrations at the end
MIGRATIONS: List[Migration] = [
    Migration(
        version=1,
        name="create_migrations_table",
        description="Create the migrations tracking table",
        sql="""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            execution_time_ms INTEGER
        );
        """,
        rollback_sql="DROP TABLE IF EXISTS schema_migrations;",
    ),
    Migration(
        version=2,
        name="create_session_reports_table",
        description="Create table for persisting session reports",
        sql="""
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
        );
        
        CREATE INDEX IF NOT EXISTS idx_session_reports_case 
            ON session_reports(case_id);
        CREATE INDEX IF NOT EXISTS idx_session_reports_status 
            ON session_reports(status);
        CREATE INDEX IF NOT EXISTS idx_session_reports_created 
            ON session_reports(created_at);
        """,
        rollback_sql="DROP TABLE IF EXISTS session_reports;",
    ),
    Migration(
        version=3,
        name="create_investigation_state_table",
        description="Create table for persisting investigation pipeline state",
        sql="""
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
        );
        
        CREATE INDEX IF NOT EXISTS idx_inv_state_status 
            ON investigation_state(status);
        CREATE INDEX IF NOT EXISTS idx_inv_state_expires 
            ON investigation_state(expires_at);
        
        -- Function to automatically update updated_at
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        
        DROP TRIGGER IF EXISTS update_investigation_state_updated_at 
            ON investigation_state;
        CREATE TRIGGER update_investigation_state_updated_at
            BEFORE UPDATE ON investigation_state
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """,
        rollback_sql="""
        DROP TABLE IF EXISTS investigation_state;
        DROP FUNCTION IF EXISTS update_updated_at_column();
        """,
    ),
    Migration(
        version=4,
        name="add_user_authentication_tables",
        description="Create tables for user authentication and audit",
        sql="""
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
        );
        
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_token VARCHAR(255) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            ip_address INET,
            user_agent TEXT
        );
        
        CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);
        
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
        );
        
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource_type, resource_id);
        """,
        rollback_sql="""
        DROP TABLE IF EXISTS audit_log;
        DROP TABLE IF EXISTS user_sessions;
        DROP TABLE IF EXISTS users;
        """,
    ),
    Migration(
        version=5,
        name="create_forensic_core_tables",
        description="Create tables for forensic tracking and evidence",
        sql="""
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
        
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
        CREATE INDEX IF NOT EXISTS idx_coc_session ON chain_of_custody(session_id);
        CREATE INDEX IF NOT EXISTS idx_coc_agent ON chain_of_custody(agent_id);
        CREATE INDEX IF NOT EXISTS idx_coc_timestamp ON chain_of_custody(timestamp_utc);
        CREATE INDEX IF NOT EXISTS idx_coc_entry_type ON chain_of_custody(entry_type);

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
        CREATE INDEX IF NOT EXISTS idx_ev_root ON evidence_artifacts(root_id);
        CREATE INDEX IF NOT EXISTS idx_ev_session ON evidence_artifacts(session_id);
        CREATE INDEX IF NOT EXISTS idx_ev_parent ON evidence_artifacts(parent_id);
        CREATE INDEX IF NOT EXISTS idx_ev_type ON evidence_artifacts(artifact_type);

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
        CREATE INDEX IF NOT EXISTS idx_cal_agent ON calibration_models(agent_id);

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
        CREATE INDEX IF NOT EXISTS idx_hitl_session ON hitl_checkpoints(session_id);
        CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_checkpoints(status);

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
        CREATE INDEX IF NOT EXISTS idx_iac_session ON inter_agent_calls(session_id);
        CREATE INDEX IF NOT EXISTS idx_iac_caller ON inter_agent_calls(caller_agent_id);
        CREATE INDEX IF NOT EXISTS idx_iac_callee ON inter_agent_calls(callee_agent_id);

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
        CREATE INDEX IF NOT EXISTS idx_tribunal_session ON tribunal_cases(session_id);

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
        CREATE INDEX IF NOT EXISTS idx_reports_session ON forensic_reports(session_id);
        CREATE INDEX IF NOT EXISTS idx_reports_case ON forensic_reports(case_id);
        """,
        rollback_sql="""
        DROP TABLE IF EXISTS forensic_reports;
        DROP TABLE IF EXISTS tribunal_cases;
        DROP TABLE IF EXISTS inter_agent_calls;
        DROP TABLE IF EXISTS hitl_checkpoints;
        DROP TABLE IF EXISTS calibration_models;
        DROP TABLE IF EXISTS evidence_artifacts;
        DROP TABLE IF EXISTS chain_of_custody;
        """,
    ),
]


class MigrationManager:
    """Manages database migrations."""
    
    def __init__(self, client: Optional[PostgresClient] = None):
        self._owned_client = client is None
        self.client = client  # Will be set to singleton in connect()
        self._connected = False
    
    async def connect(self):
        """Connect to the database — always uses the singleton pool."""
        if not self._connected:
            if self.client is None:
                self.client = await get_postgres_client()
            self._connected = True
    
    async def disconnect(self):
        """No-op when using singleton; only disconnect if client was externally provided."""
        if self._connected and not self._owned_client:
            # Singleton — don't close the shared pool
            self._connected = False
        elif self._connected and self._owned_client and self.client:
            await self.client.disconnect()
            self._connected = False
    
    async def get_applied_migrations(self) -> List[int]:
        """Get list of applied migration versions."""
        try:
            # Check existence first to avoid a postgres ERROR log on first start
            exists = await self.client.fetch_val(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'schema_migrations'
                )
                """
            )
            if not exists:
                return []
            result = await self.client.fetch(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
            return [row["version"] for row in result]
        except Exception as e:
            # Table might not exist yet
            logger.debug("Could not fetch migrations", error=str(e))
            return []
    
    async def apply_migration(self, migration: Migration) -> bool:
        """Apply a single migration within an explicit asyncpg transaction (atomic)."""
        import time

        start_time = time.time()
        logger.info(
            "Applying migration",
            version=migration.version,
            name=migration.name,
        )

        try:
            async with self.client.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(migration.sql)

                    execution_time = int((time.time() - start_time) * 1000)

                    await conn.execute(
                        """
                        INSERT INTO schema_migrations (version, name, description, execution_time_ms)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (version) DO UPDATE SET
                            applied_at = NOW(),
                            execution_time_ms = $4
                        """,
                        migration.version,
                        migration.name,
                        migration.description,
                        execution_time,
                    )

            logger.info(
                "Migration applied successfully",
                version=migration.version,
                name=migration.name,
                execution_time_ms=int((time.time() - start_time) * 1000),
            )
            return True

        except Exception as e:
            logger.error(
                "Migration failed",
                version=migration.version,
                name=migration.name,
                error=str(e),
            )
            return False
    
    async def rollback_migration(self, migration: Migration) -> bool:
        """Rollback a single migration within an explicit asyncpg transaction (atomic)."""
        if not migration.rollback_sql:
            logger.warning(
                "No rollback SQL for migration",
                version=migration.version,
                name=migration.name,
            )
            return False

        logger.info(
            "Rolling back migration",
            version=migration.version,
            name=migration.name,
        )

        try:
            async with self.client.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(migration.rollback_sql)
                    await conn.execute(
                        "DELETE FROM schema_migrations WHERE version = $1",
                        migration.version,
                    )

            logger.info(
                "Migration rolled back successfully",
                version=migration.version,
                name=migration.name,
            )
            return True

        except Exception as e:
            logger.error(
                "Rollback failed",
                version=migration.version,
                name=migration.name,
                error=str(e),
            )
            return False
    
    async def migrate(self, target_version: Optional[int] = None) -> bool:
        """
        Apply all pending migrations up to target_version.
        
        Args:
            target_version: Target migration version. If None, applies all.
        
        Returns:
            True if all migrations applied successfully
        """
        await self.connect()
        
        try:
            applied = await self.get_applied_migrations()
            
            # Always ensure migrations table exists first
            if 1 not in applied:
                migration_1 = next(m for m in MIGRATIONS if m.version == 1)
                if not await self.apply_migration(migration_1):
                    return False
                applied = [1]
            
            pending = [
                m for m in MIGRATIONS
                if m.version not in applied
                and (target_version is None or m.version <= target_version)
            ]
            
            if not pending:
                logger.info("No pending migrations")
                return True
            
            logger.info(f"Applying {len(pending)} migration(s)")
            
            for migration in pending:
                if not await self.apply_migration(migration):
                    return False
            
            logger.info("All migrations applied successfully")
            return True
            
        except Exception as e:
            logger.error("Migration failed", error=str(e))
            return False
    
    async def rollback(self, target_version: int) -> bool:
        """
        Rollback migrations to target_version.
        
        Args:
            target_version: Target migration version to rollback to.
        
        Returns:
            True if rollback successful
        """
        await self.connect()
        
        try:
            applied = await self.get_applied_migrations()
            to_rollback = [
                m for m in MIGRATIONS
                if m.version in applied and m.version > target_version
            ]
            # Rollback in reverse order
            to_rollback.reverse()
            
            if not to_rollback:
                logger.info("No migrations to rollback")
                return True
            
            logger.info(f"Rolling back {len(to_rollback)} migration(s)")
            
            for migration in to_rollback:
                if not await self.rollback_migration(migration):
                    return False
            
            logger.info("Rollback completed successfully")
            return True
            
        except Exception as e:
            logger.error("Rollback failed", error=str(e))
            return False
    
    async def status(self) -> dict:
        """Get current migration status."""
        try:
            await self.connect()
            
            applied = await self.get_applied_migrations()
            pending = [m.version for m in MIGRATIONS if m.version not in applied]
            
            return {
                "current_version": max(applied) if applied else 0,
                "latest_version": max(m.version for m in MIGRATIONS),
                "applied_count": len(applied),
                "pending_count": len(pending),
                "pending_versions": pending,
                "is_current": len(pending) == 0,
            }
        finally:
            if self._owned_client:
                await self.disconnect()


async def run_migrations():
    """Run all pending migrations."""
    manager = MigrationManager()
    try:
        success = await manager.migrate()
        status = await manager.status()
        await manager.disconnect()
        
        if success:
            logger.info(
                "Database is up to date",
                version=status["current_version"],
            )
        return success
    except Exception as e:
        logger.error("Migration error", error=str(e))
        return False


if __name__ == "__main__":
    import sys
    
    # Allow command-line usage
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        manager = MigrationManager()
        result = asyncio.run(manager.status())
        print(f"Current version: {result['current_version']}")
        print(f"Latest version: {result['latest_version']}")
        print(f"Pending migrations: {result['pending_count']}")
        if result['pending_versions']:
            print(f"Pending: {result['pending_versions']}")
        asyncio.run(manager.disconnect())
    else:
        success = asyncio.run(run_migrations())
        sys.exit(0 if success else 1)
