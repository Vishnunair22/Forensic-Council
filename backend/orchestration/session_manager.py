"""
Session Manager for Forensic Council
====================================

Manages active investigation sessions, agent loops, and HITL checkpoints.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

import json

from core.structured_logging import get_logger

logger = get_logger(__name__)


class SessionStatus(str, Enum):
    """Status of an investigation session."""
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    AWAITING_HITL = "AWAITING_HITL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CheckpointStatus(str, Enum):
    """Status of a HITL checkpoint."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


@dataclass
class HITLCheckpointState:
    """State of a human-in-the-loop checkpoint."""
    checkpoint_id: UUID
    session_id: UUID
    agent_id: str
    checkpoint_type: str
    description: str
    pending_content: dict[str, Any]
    status: CheckpointStatus = CheckpointStatus.PENDING
    human_decision: Optional[dict[str, Any]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None


@dataclass
class AgentLoopState:
    """State of an agent's investigation loop."""
    agent_id: str
    session_id: UUID
    status: SessionStatus
    current_iteration: int = 0
    findings: list[dict[str, Any]] = field(default_factory=list)
    pending_checkpoints: list[UUID] = field(default_factory=list)


@dataclass
class SessionState:
    """Complete state of an investigation session."""
    session_id: UUID
    case_id: str
    investigator_id: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    agent_loops: dict[str, AgentLoopState] = field(default_factory=dict)
    checkpoints: dict[UUID, HITLCheckpointState] = field(default_factory=dict)
    final_report_id: Optional[UUID] = None


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
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        async with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
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
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
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
    
    async def get_session(self, session_id: UUID) -> Optional[SessionState]:
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
                session.updated_at = datetime.now(timezone.utc)
                
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
                session.updated_at = datetime.now(timezone.utc)
                
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
            session.agent_loops[agent_id].pending_checkpoints.append(checkpoint.checkpoint_id)
            session.status = SessionStatus.AWAITING_HITL
            session.updated_at = datetime.now(timezone.utc)
            
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
                    checkpoint.status = CheckpointStatus(decision.get("status", "APPROVED"))
                    checkpoint.human_decision = decision
                    checkpoint.resolved_at = datetime.now(timezone.utc)
                    
                    # Remove from pending
                    session.agent_loops[checkpoint.agent_id].pending_checkpoints.remove(checkpoint_id)
                    
                    # Check if any pending checkpoints remain
                    has_pending = any(
                        cp.status == CheckpointStatus.PENDING
                        for cp in session.checkpoints.values()
                    )
                    if not has_pending:
                        session.status = SessionStatus.RUNNING
                    
                    session.updated_at = datetime.now(timezone.utc)
                    
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
            cp for cp in session.checkpoints.values()
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
                session.updated_at = datetime.now(timezone.utc)
                
                if self._redis:
                    await self._persist_session(session)
    
    async def _persist_session(self, session: SessionState) -> None:
        """Persist full session state to Redis."""
        if not self._redis:
            return
        
        key = f"session:{session.session_id}"
        
        # Serialize agent loops
        agent_loops_data = {}
        for aid, loop in session.agent_loops.items():
            agent_loops_data[aid] = {
                "agent_id": loop.agent_id,
                "session_id": str(loop.session_id),
                "status": loop.status.value,
                "current_iteration": loop.current_iteration,
                "findings": loop.findings,
                "pending_checkpoints": [str(cid) for cid in loop.pending_checkpoints],
            }
            
        # Serialize checkpoints
        checkpoints_data = {}
        for cid, cp in session.checkpoints.items():
            checkpoints_data[str(cid)] = {
                "checkpoint_id": str(cp.checkpoint_id),
                "session_id": str(cp.session_id),
                "agent_id": cp.agent_id,
                "checkpoint_type": cp.checkpoint_type,
                "description": cp.description,
                "pending_content": cp.pending_content,
                "status": cp.status.value,
                "human_decision": cp.human_decision,
                "created_at": cp.created_at.isoformat(),
                "resolved_at": cp.resolved_at.isoformat() if cp.resolved_at else None,
            }
            
        data = {
            "session_id": str(session.session_id),
            "case_id": session.case_id,
            "investigator_id": session.investigator_id,
            "status": session.status.value,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "final_report_id": str(session.final_report_id) if session.final_report_id else None,
            "agent_loops": agent_loops_data,
            "checkpoints": checkpoints_data,
        }
        await self._redis.set(key, json.dumps(data), ex=86400)
    
    async def _load_session(self, session_id: UUID) -> None:
        """Load session from Redis and hydrate in-memory cache."""
        if not self._redis:
            return
        
        key = f"session:{session_id}"
        data_str = await self._redis.get(key)
        if data_str:
            try:
                data = json.loads(data_str)
                
                # Reconstruct agent loops
                agent_loops = {}
                for aid, l_data in data.get("agent_loops", {}).items():
                    agent_loops[aid] = AgentLoopState(
                        agent_id=l_data["agent_id"],
                        session_id=UUID(l_data["session_id"]),
                        status=SessionStatus(l_data["status"]),
                        current_iteration=l_data.get("current_iteration", 0),
                        findings=l_data.get("findings", []),
                        pending_checkpoints=[UUID(cid) for cid in l_data.get("pending_checkpoints", [])],
                    )
                
                # Reconstruct checkpoints
                checkpoints = {}
                for cid_str, cp_data in data.get("checkpoints", {}).items():
                    checkpoints[UUID(cid_str)] = HITLCheckpointState(
                        checkpoint_id=UUID(cp_data["checkpoint_id"]),
                        session_id=UUID(cp_data["session_id"]),
                        agent_id=cp_data["agent_id"],
                        checkpoint_type=cp_data["checkpoint_type"],
                        description=cp_data["description"],
                        pending_content=cp_data["pending_content"],
                        status=CheckpointStatus(cp_data["status"]),
                        human_decision=cp_data.get("human_decision"),
                        created_at=datetime.fromisoformat(cp_data["created_at"]),
                        resolved_at=datetime.fromisoformat(cp_data["resolved_at"]) if cp_data.get("resolved_at") else None,
                    )
                
                session = SessionState(
                    session_id=UUID(data["session_id"]),
                    case_id=data["case_id"],
                    investigator_id=data["investigator_id"],
                    status=SessionStatus(data["status"]),
                    created_at=datetime.fromisoformat(data["created_at"]),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                    agent_loops=agent_loops,
                    checkpoints=checkpoints,
                    final_report_id=UUID(data["final_report_id"]) if data.get("final_report_id") else None,
                )
                
                self._sessions[session_id] = session
            except Exception as e:
                logger.error(f"Failed to load session {session_id} from Redis", error=str(e))
