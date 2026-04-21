"""
Session Persistence Module
==========================

Persists investigation session state to PostgreSQL.
Replaces in-memory storage for production scalability.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from core.config import get_settings
from core.persistence.postgres_client import PostgresClient, get_postgres_client
from core.structured_logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class SessionPersistence:
    """Handles persistence of investigation session state."""

    def __init__(self, client: PostgresClient | None = None):
        self.client = client
        self._owned_client = False  # Never own the client — always use the singleton

    async def _ensure_client(self):
        """Ensure database client is connected — always reuse the singleton pool."""
        if self.client is None:
            try:
                self.client = await asyncio.wait_for(
                    get_postgres_client(), timeout=10.0
                )
            except TimeoutError:
                raise RuntimeError(
                    "Database connection timed out after 10s in session persistence"
                )

    async def close(self):
        """No-op: we don't own the singleton client."""
        pass

    async def save_session_state(
        self,
        session_id: str,
        case_id: str,
        investigator_id: str,
        pipeline_state: dict,
        status: str = "running",
    ) -> bool:
        """
        Save session state to database.

        Args:
            session_id: Unique session identifier
            case_id: Case identifier
            investigator_id: Investigator identifier
            pipeline_state: Serialized pipeline state
            status: Session status

        Returns:
            True if saved successfully
        """
        await self._ensure_client()
        if self.client is None:
            logger.warning("SessionPersistence.save_session: database client not available")
            return False

        try:
            expires_at = datetime.now(UTC) + timedelta(hours=24)

            await self.client.execute(
                """
                INSERT INTO investigation_state
                    (session_id, case_id, investigator_id, pipeline_state, status, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (session_id) DO UPDATE SET
                    pipeline_state = $4,
                    status = $5,
                    updated_at = NOW(),
                    expires_at = $6
                """,
                UUID(session_id),
                case_id,
                investigator_id,
                json.dumps(pipeline_state, default=str),
                status,
                expires_at,
            )

            logger.debug("Session state saved", session_id=session_id, status=status)
            return True

        except Exception as e:
            logger.error(
                "Failed to save session state", session_id=session_id, error=str(e)
            )
            return False

    async def get_session_state(self, session_id: str) -> dict | None:
        """
        Retrieve session state from database.

        Args:
            session_id: Session identifier

        Returns:
            Session state dict or None
        """
        await self._ensure_client()
        if self.client is None:
            logger.warning("SessionPersistence.get_session_state: database client not available")
            return None

        try:
            result = await self.client.fetch_one(
                """
                SELECT session_id, case_id, investigator_id, pipeline_state,
                       agent_results, checkpoints, status, created_at, updated_at
                FROM investigation_state
                WHERE session_id = $1 AND expires_at > NOW()
                """,
                UUID(session_id),
            )

            if result:
                return {
                    "session_id": str(result["session_id"]),
                    "case_id": result["case_id"],
                    "investigator_id": result["investigator_id"],
                    "pipeline_state": result["pipeline_state"],
                    "agent_results": result["agent_results"],
                    "checkpoints": result["checkpoints"],
                    "status": result["status"],
                    "created_at": result["created_at"].isoformat()
                    if result["created_at"]
                    else None,
                    "updated_at": result["updated_at"].isoformat()
                    if result["updated_at"]
                    else None,
                }
            return None

        except Exception as e:
            logger.error(
                "Failed to get session state", session_id=session_id, error=str(e)
            )
            return None

    async def save_report(
        self,
        session_id: str,
        case_id: str,
        investigator_id: str,
        report_data: dict,
    ) -> bool:
        """
        Save final investigation report.

        Args:
            session_id: Session identifier
            case_id: Case identifier
            investigator_id: Investigator identifier
            report_data: Serialized report data

        Returns:
            True if saved successfully
        """
        await self._ensure_client()
        if self.client is None:
            logger.warning("SessionPersistence.save_report: database client not available")
            return False

        try:
            await self.client.execute(
                """
                INSERT INTO session_reports
                    (session_id, case_id, investigator_id, status, completed_at, report_data)
                VALUES ($1, $2, $3, $4, NOW(), $5)
                ON CONFLICT (session_id) DO UPDATE SET
                    report_data = $5,
                    status = $4,
                    completed_at = NOW()
                """,
                UUID(session_id),
                case_id,
                investigator_id,
                "completed",
                report_data,
            )

            logger.debug("Report saved", session_id=session_id)
            return True

        except Exception as e:
            logger.error("Failed to save report", session_id=session_id, error=str(e))
            return False

    async def get_report(self, session_id: str) -> dict | None:
        """
        Retrieve saved report.

        Args:
            session_id: Session identifier

        Returns:
            Report data dict or None
        """
        await self._ensure_client()
        if self.client is None:
            logger.warning("SessionPersistence.get_report: database client not available")
            return None

        try:
            result = await self.client.fetch_one(
                """
                SELECT session_id, case_id, investigator_id, status,
                       completed_at, report_data, error_message
                FROM session_reports
                WHERE session_id = $1
                """,
                UUID(session_id),
            )

            if result:
                report_data = result["report_data"]
                if isinstance(report_data, str):
                    try:
                        report_data = json.loads(report_data)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Stored report_data was not valid JSON",
                            session_id=session_id,
                        )
                        report_data = {}
                return {
                    "session_id": str(result["session_id"]),
                    "case_id": result["case_id"],
                    "investigator_id": result["investigator_id"],
                    "status": result["status"],
                    "completed_at": result["completed_at"].isoformat()
                    if result["completed_at"]
                    else None,
                    "report_data": report_data,
                    "error_message": result["error_message"],
                }
            return None

        except Exception as e:
            logger.error("Failed to get report", session_id=session_id, error=str(e))
            return None

    async def update_session_status(
        self,
        session_id: str,
        status: str,
        error_message: str | None = None,
    ) -> bool:
        """
        Update session status.

        Args:
            session_id: Session identifier
            status: New status
            error_message: Optional error message

        Returns:
            True if updated successfully
        """
        await self._ensure_client()
        if self.client is None:
            logger.warning("SessionPersistence.update_session_status: database client not available")
            return False

        try:
            if error_message:
                await self.client.execute(
                    """
                    UPDATE investigation_state
                    SET status = $2, updated_at = NOW()
                    WHERE session_id = $1
                    """,
                    UUID(session_id),
                    status,
                )

                # Update session_reports if a row already exists (error status + message)
                # We use UPDATE not INSERT to avoid NOT NULL violations on case_id/investigator_id
                # (those fields are only available at investigation start, not in the error callback)
                await self.client.execute(
                    """
                    UPDATE session_reports
                    SET status = $2, error_message = $3
                    WHERE session_id = $1
                    """,
                    UUID(session_id),
                    status,
                    error_message,
                )
            else:
                await self.client.execute(
                    """
                    UPDATE investigation_state
                    SET status = $2, updated_at = NOW()
                    WHERE session_id = $1
                    """,
                    UUID(session_id),
                    status,
                )

            return True

        except Exception as e:
            logger.error("Failed to update status", session_id=session_id, error=str(e))
            return False

    async def list_active_sessions(self, case_id: str | None = None) -> list:
        """
        List active sessions.

        Args:
            case_id: Optional case filter

        Returns:
            List of session summaries
        """
        await self._ensure_client()
        if self.client is None:
            logger.warning("SessionPersistence.list_active_sessions: database client not available")
            return []

        try:
            if case_id:
                result = await self.client.fetch(
                    """
                    SELECT session_id, case_id, investigator_id, status, created_at, updated_at
                    FROM investigation_state
                    WHERE case_id = $1 AND status IN ('running', 'pending')
                    AND expires_at > NOW()
                    ORDER BY created_at DESC
                    """,
                    case_id,
                )
            else:
                result = await self.client.fetch(
                    """
                    SELECT session_id, case_id, investigator_id, status, created_at, updated_at
                    FROM investigation_state
                    WHERE status IN ('running', 'pending')
                    AND expires_at > NOW()
                    ORDER BY created_at DESC
                    """
                )

            return [
                {
                    "session_id": str(row["session_id"]),
                    "case_id": row["case_id"],
                    "investigator_id": row["investigator_id"],
                    "status": row["status"],
                    "created_at": row["created_at"].isoformat()
                    if row["created_at"]
                    else None,
                    "updated_at": row["updated_at"].isoformat()
                    if row["updated_at"]
                    else None,
                }
                for row in result
            ]

        except Exception as e:
            logger.error("Failed to list sessions", error=str(e))
            return []

    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired session states.

        Returns:
            Number of sessions cleaned up
        """
        await self._ensure_client()
        if self.client is None:
            logger.warning("SessionPersistence.cleanup_expired_sessions: database client not available")
            return 0

        try:
            result = await self.client.execute(
                """
                DELETE FROM investigation_state
                WHERE expires_at < NOW()
                """
            )

            count = result.split()[-1] if isinstance(result, str) else "0"
            logger.info("Cleaned up expired sessions", count=count)
            return int(count) if count.isdigit() else 0

        except Exception as e:
            logger.error("Failed to cleanup sessions", error=str(e))
            return 0


# Global persistence instance
_session_persistence: SessionPersistence | None = None


async def get_session_persistence() -> SessionPersistence:
    """Get or create global session persistence instance."""
    global _session_persistence
    if _session_persistence is None:
        _session_persistence = SessionPersistence()
        await _session_persistence._ensure_client()
    return _session_persistence


async def close_session_persistence():
    """Close global session persistence."""
    global _session_persistence
    if _session_persistence:
        await _session_persistence.close()
        _session_persistence = None
