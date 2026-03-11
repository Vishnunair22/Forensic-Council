"""
Session Persistence Module
==========================

Persists investigation session state to PostgreSQL.
Replaces in-memory storage for production scalability.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from core.config import get_settings
from core.logging import get_logger
from infra.postgres_client import PostgresClient
from core.retry import with_retry, get_retry_config, retry_async

logger = get_logger(__name__)
settings = get_settings()


class SessionPersistence:
    """Handles persistence of investigation session state."""
    
    def __init__(self, client: Optional[PostgresClient] = None):
        self.client = client
        self._owned_client = client is None
    
    async def _ensure_client(self):
        """Ensure database client is connected."""
        if self.client is None:
            self.client = PostgresClient()
        if not hasattr(self.client, '_connected') or not self.client._connected:
            await retry_async(
                self.client.connect,
                config=get_retry_config("database"),
            )
    
    async def close(self):
        """Close database connection if owned."""
        if self._owned_client and self.client:
            await self.client.disconnect()
    
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
        
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            
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
                json.dumps(pipeline_state),
                status,
                expires_at,
            )
            
            logger.debug("Session state saved", session_id=session_id, status=status)
            return True
            
        except Exception as e:
            logger.error("Failed to save session state", session_id=session_id, error=str(e))
            return False
    
    async def get_session_state(self, session_id: str) -> Optional[dict]:
        """
        Retrieve session state from database.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Session state dict or None
        """
        await self._ensure_client()
        
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
                    "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                    "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
                }
            return None
            
        except Exception as e:
            logger.error("Failed to get session state", session_id=session_id, error=str(e))
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
                json.dumps(report_data),
            )
            
            logger.debug("Report saved", session_id=session_id)
            return True
            
        except Exception as e:
            logger.error("Failed to save report", session_id=session_id, error=str(e))
            return False
    
    async def get_report(self, session_id: str) -> Optional[dict]:
        """
        Retrieve saved report.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Report data dict or None
        """
        await self._ensure_client()
        
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
                return {
                    "session_id": str(result["session_id"]),
                    "case_id": result["case_id"],
                    "investigator_id": result["investigator_id"],
                    "status": result["status"],
                    "completed_at": result["completed_at"].isoformat() if result["completed_at"] else None,
                    "report_data": result["report_data"],
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
        error_message: Optional[str] = None,
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
                
                # Also update reports table with error
                await self.client.execute(
                    """
                    INSERT INTO session_reports (session_id, case_id, investigator_id, status, error_message)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (session_id) DO UPDATE SET
                        status = $4,
                        error_message = $5
                    """,
                    UUID(session_id),
                    "",  # case_id - NOT NULL but not available here
                    "",  # investigator_id - NOT NULL but not available here
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
    
    async def list_active_sessions(self, case_id: Optional[str] = None) -> list:
        """
        List active sessions.
        
        Args:
            case_id: Optional case filter
        
        Returns:
            List of session summaries
        """
        await self._ensure_client()
        
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
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
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
_session_persistence: Optional[SessionPersistence] = None


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
