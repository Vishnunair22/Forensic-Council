"""
Session Manager for Forensic Council
====================================

Manages active investigation sessions, agent loops, and HITL checkpoints.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.structured_logging import get_logger

logger = get_logger(__name__)


class SessionStatus(StrEnum):
    """Status of an investigation session."""

    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    AWAITING_HITL = "AWAITING_HITL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CheckpointStatus(StrEnum):
    """Status of a HITL checkpoint."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


class HITLCheckpointState(BaseModel):
    """State of a human-in-the-loop checkpoint."""

    checkpoint_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    agent_id: str
    checkpoint_type: str
    description: str
    pending_content: dict[str, Any]
    status: CheckpointStatus = CheckpointStatus.PENDING
    human_decision: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None


class AgentLoopState(BaseModel):
    """State of an agent's investigation loop."""

    agent_id: str
    session_id: UUID
    status: SessionStatus
    current_iteration: int = 0
    findings: list[dict[str, Any]] = Field(default_factory=list)
    pending_checkpoints: list[UUID] = Field(default_factory=list)


class SessionState(BaseModel):
    """Complete state of an investigation session."""

    session_id: UUID
    case_id: str
    investigator_id: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    agent_loops: dict[str, AgentLoopState] = Field(default_factory=dict)
    checkpoints: dict[UUID, HITLCheckpointState] = Field(default_factory=dict)
    final_report_id: UUID | None = None


class SessionManager:
    """
    Manages active investigation sessions, tracks agent loops, and handles
    human-in-the-loop (HITL) checkpoints.
    """

    def __init__(self, redis_client: Any = None):
        self._redis = redis_client
        self._sessions: dict[UUID, SessionState] = {}
        self._lock = asyncio.Lock()

    _MAX_SESSIONS = 500  # Hard cap to prevent unbounded memory growth

    async def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """Evict completed/failed sessions older than max_age_hours to prevent unbounded memory growth."""
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        async with self._lock:
            expired = [
                sid
                for sid, s in self._sessions.items()
                if s.updated_at < cutoff
                and s.status in (SessionStatus.COMPLETED, SessionStatus.FAILED)
            ]
            for sid in expired:
                del self._sessions[sid]
        if expired:
            logger.info("Evicted stale sessions", count=len(expired))
        return len(expired)

    async def create_session(
        self,
        session_id: UUID,
        case_id: str,
        investigator_id: str,
        agent_ids: list[str],
    ) -> SessionState:
        """Create a new investigation session."""
        # Opportunistic cleanup on every creation
        if len(self._sessions) > self._MAX_SESSIONS:
            await self.cleanup_old_sessions(max_age_hours=6)

        async with self._lock:
            session = SessionState(
                session_id=session_id,
                case_id=case_id,
                investigator_id=investigator_id,
                status=SessionStatus.INITIALIZING,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                agent_loops={
                    agent_id: AgentLoopState(
                        agent_id=agent_id,
                        session_id=session_id,
                        status=SessionStatus.INITIALIZING,
                    )
                    for agent_id in agent_ids
                },
            )
            self._sessions[session_id] = session

            # Persist to Redis if available
            if self._redis:
                await self._persist_session(session)

            return session

    async def get_session(self, session_id: UUID) -> SessionState | None:
        """Get session state by ID."""
        if self._redis:
            await self._load_session(session_id)
        return self._sessions.get(session_id)

    async def update_agent_status(
        self,
        session_id: UUID,
        agent_id: str,
        status: SessionStatus,
    ) -> None:
        """Update an agent's loop status."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session and agent_id in session.agent_loops:
                session.agent_loops[agent_id].status = status
                session.updated_at = datetime.now(UTC)

                # Check if all agents are done
                all_done = all(
                    loop.status in (SessionStatus.COMPLETED, SessionStatus.FAILED)
                    for loop in session.agent_loops.values()
                )
                if all_done:
                    session.status = SessionStatus.COMPLETED

                if self._redis:
                    await self._persist_session(session)

    async def add_findings(
        self,
        session_id: UUID,
        agent_id: str,
        findings: list[dict[str, Any]],
    ) -> None:
        """Add findings from an agent."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session and agent_id in session.agent_loops:
                session.agent_loops[agent_id].findings.extend(findings)
                session.updated_at = datetime.now(UTC)

                if self._redis:
                    await self._persist_session(session)

    async def add_checkpoint(
        self,
        session_id: UUID,
        agent_id: str,
        checkpoint_type: str,
        description: str,
        pending_content: dict[str, Any],
    ) -> HITLCheckpointState:
        """Add a HITL checkpoint to a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            checkpoint = HITLCheckpointState(
                checkpoint_id=uuid4(),
                session_id=session_id,
                agent_id=agent_id,
                checkpoint_type=checkpoint_type,
                description=description,
                pending_content=pending_content,
            )

            session.checkpoints[checkpoint.checkpoint_id] = checkpoint
            session.agent_loops[agent_id].pending_checkpoints.append(
                checkpoint.checkpoint_id
            )
            session.status = SessionStatus.AWAITING_HITL
            session.updated_at = datetime.now(UTC)

            if self._redis:
                await self._persist_session(session)

            return checkpoint

    async def resolve_checkpoint(
        self,
        checkpoint_id: UUID,
        decision: dict[str, Any],
    ) -> None:
        """Resolve a HITL checkpoint with human decision."""
        async with self._lock:
            for session in self._sessions.values():
                if checkpoint_id in session.checkpoints:
                    checkpoint = session.checkpoints[checkpoint_id]
                    checkpoint.status = CheckpointStatus(
                        decision.get("status", "APPROVED")
                    )
                    checkpoint.human_decision = decision
                    checkpoint.resolved_at = datetime.now(UTC)

                    # Remove from pending
                    session.agent_loops[checkpoint.agent_id].pending_checkpoints.remove(
                        checkpoint_id
                    )

                    # Check if any pending checkpoints remain
                    has_pending = any(
                        cp.status == CheckpointStatus.PENDING
                        for cp in session.checkpoints.values()
                    )
                    if not has_pending:
                        session.status = SessionStatus.RUNNING

                    session.updated_at = datetime.now(UTC)

                    if self._redis:
                        await self._persist_session(session)

                    return

            raise ValueError(f"Checkpoint {checkpoint_id} not found")

    async def get_active_checkpoints(
        self,
        session_id: UUID,
    ) -> list[HITLCheckpointState]:
        """Get all active checkpoints for a session."""
        session = await self.get_session(session_id)
        if not session:
            return []

        return [
            cp
            for cp in session.checkpoints.values()
            if cp.status == CheckpointStatus.PENDING
        ]

    async def get_investigator_brief(
        self,
        session_id: UUID,
        agent_id: str,
    ) -> str:
        """Get a briefing string for the investigator about an agent's status."""
        session = await self.get_session(session_id)
        if not session:
            return f"Session {session_id} not found"

        agent_loop = session.agent_loops.get(agent_id)
        if not agent_loop:
            return f"Agent {agent_id} not found in session"

        brief_lines = [
            f"Session: {session.case_id}",
            f"Agent: {agent_id}",
            f"Status: {agent_loop.status}",
            f"Iteration: {agent_loop.current_iteration}",
            f"Findings: {len(agent_loop.findings)}",
        ]

        pending = await self.get_active_checkpoints(session_id)
        agent_pending = [cp for cp in pending if cp.agent_id == agent_id]
        if agent_pending:
            brief_lines.append(f"Pending Checkpoints: {len(agent_pending)}")
            for cp in agent_pending:
                brief_lines.append(f"  - {cp.checkpoint_type}: {cp.description}")

        return "\n".join(brief_lines)

    async def set_final_report(
        self,
        session_id: UUID,
        report_id: UUID,
    ) -> None:
        """Set the final report ID for a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.final_report_id = report_id
                session.status = SessionStatus.COMPLETED
                session.updated_at = datetime.now(UTC)

                if self._redis:
                    await self._persist_session(session)

    async def _persist_session(self, session: SessionState) -> None:
        """Persist full session state to Redis."""
        if not self._redis:
            return

        key = f"session:{session.session_id}"
        try:
            # IMPV-01: Session metadata is transient; 4-hour TTL prevents unbounded growth.
            await self._redis.set(key, session.model_dump_json(), ex=14400)
        except Exception as e:
            logger.error(f"Failed to persist session {session.session_id} to Redis", error=str(e))

    async def _load_session(self, session_id: UUID) -> None:
        """Load session from Redis and hydrate in-memory cache."""
        if not self._redis:
            return

        key = f"session:{session_id}"
        data_str = await self._redis.get(key)
        if data_str:
            try:
                session = SessionState.model_validate_json(data_str)
                self._sessions[session_id] = session
            except Exception as e:
                logger.error(
                    f"Failed to load session {session_id} from Redis",
                    error=str(e),
                    exc_info=True,
                )
