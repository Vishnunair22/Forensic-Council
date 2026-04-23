"""
Inter-Agent Communication Protocol
==================================

Implements the inter-agent communication protocol with anti-circular dependency enforcement.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.agent_registry import get_agent_registry
from core.exceptions import (
    ArbiterRechallengeError,
    CircularCallError,
    PermittedCallViolationError,
)
from core.structured_logging import get_logger

logger = get_logger(__name__)


class InterAgentCallType(StrEnum):
    """Types of inter-agent calls."""

    COLLABORATIVE = "COLLABORATIVE"  # Request for additional analysis
    CHALLENGE = "CHALLENGE"  # Arbiter challenge to agent finding


class InterAgentCall(BaseModel):
    """
    Inter-agent call request model.

    Represents a call from one agent to another for collaborative analysis
    or challenge resolution.
    """

    call_id: UUID = Field(default_factory=uuid4)
    caller_agent_id: str
    callee_agent_id: str
    call_type: InterAgentCallType
    artifact_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] | None = None
    status: Literal["PENDING", "COMPLETE", "FAILED"] = "PENDING"
    created_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_utc: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "call_id": str(self.call_id),
            "caller_agent_id": self.caller_agent_id,
            "callee_agent_id": self.callee_agent_id,
            "call_type": self.call_type.value,
            "artifact_id": str(self.artifact_id) if self.artifact_id else None,
            "payload": self.payload,
            "response": self.response,
            "status": self.status,
            "created_utc": self.created_utc.isoformat(),
            "completed_utc": self.completed_utc.isoformat()
            if self.completed_utc
            else None,
        }


# Rules for inter-agent communication are now managed by the AgentRegistry.


class InterAgentBus:
    """
    Inter-agent communication bus with anti-circular dependency enforcement.

    Manages calls between agents, ensuring permitted paths and preventing
    circular dependencies.
    """

    # Class-level annotations so Pyright knows these instance attributes exist.
    _dispatch_lock: asyncio.Lock

    def __init__(
        self,
        config: Any | None = None,
        evidence_artifact: Any | None = None,
        session_id: UUID | None = None,
        working_memory: Any | None = None,
        episodic_memory: Any | None = None,
        custody_logger: Any | None = None,
        evidence_store: Any | None = None,
    ):
        # Store components needed to create agents on demand
        self._config = config
        self._evidence_artifact = evidence_artifact
        self._session_id = session_id
        self._working_memory = working_memory
        self._episodic_memory = episodic_memory
        self._custody_logger = custody_logger
        self._evidence_store = evidence_store

        # Track active calls: (caller, callee, artifact_id) tuples
        self._active_calls: set[tuple[str, str, str | None]] = set()
        # Track arbiter challenges: session_id → set of agent_ids that have been challenged
        self._arbiter_challenges: dict[str, set[str]] = {}
        # Track completed calls per session to detect circular patterns
        self._completed_calls: dict[str, set[tuple[str, str, str | None]]] = {}
        # Call history for audit
        self._call_history: list[InterAgentCall] = []
        # Broadcast history for session-wide notes
        self._broadcast_history: list[dict[str, Any]] = []
        # Event signaling for cross-agent coordination (native asyncio.Event)
        self._events: dict[str, asyncio.Event] = {}
        # Registered agent instances: callee_id → ForensicAgent
        self._registered_agents: dict[str, Any] = {}
        # Lock to make circular-dependency check + _active_calls registration atomic
        self._dispatch_lock = asyncio.Lock()

    def signal_event(self, session_id: Any, event_name: str, payload: dict = None) -> None:
        """Signal an event to any waiting agents. Safe from any context."""
        key = f"{session_id}:{event_name}"
        if key not in self._events:
            self._events[key] = asyncio.Event()

        if payload and "note" in event_name.lower():
            self._broadcast_history.append({
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event_name,
                "payload": payload
            })

        self._events[key].set()

    def broadcast_note(self, agent_id: str, note_type: str, content: dict) -> None:
        """
        Broadcast a forensic note to all agents in the session.
        Useful for sharing identified personas, objects, or locations.
        """
        logger.info(f"Agent {agent_id} broadcasting forensic note: {note_type}")
        self.signal_event(
            self._session_id,
            f"note:{note_type}",
            {"sender": agent_id, "content": content}
        )

    def register_agent(self, agent_id: str, agent_instance: Any) -> None:
        """Register a live agent instance for inter-agent calls.

        When a registered instance exists for *callee_agent_id*, ``send()`` will
        reuse it instead of creating a fresh agent from scratch.  This avoids
        the overhead of re-initializing working memory, episodic memory, and
        tool registries for a callee that is already running in the same
        investigation session.
        """
        self._registered_agents[agent_id] = agent_instance

    def unregister_agent(self, agent_id: str) -> None:
        """Remove a previously registered agent instance."""
        self._registered_agents.pop(agent_id, None)

    async def wait_for_event(self, session_id: Any, event_name: str, timeout: float = 60.0) -> bool:
        """Wait for a named event to be signaled. Returns True if signaled, False on timeout."""
        key = f"{session_id}:{event_name}"
        if key not in self._events:
            self._events[key] = asyncio.Event()
        evt = self._events[key]

        try:
            await asyncio.wait_for(evt.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    def is_call_permitted(self, caller: str, callee: str) -> bool:
        """Check if a call path is permitted via the central registry."""
        permitted_callees = get_agent_registry().get_permitted_callees(caller)
        return callee in permitted_callees

    def is_circular_call(
        self, caller: str, callee: str, artifact_id: UUID | None
    ) -> bool:
        """
        Check if a call would create a circular dependency.

        A circular call occurs when:
        1. Callee has an active call to caller on the same artifact
        2. Or callee has completed a call to caller on same artifact (within same loop)
        3. Or any agent in the call chain has already called the current caller

        Note: Calls without artifact_id are not checked for circularity.
        """
        artifact_str = str(artifact_id) if artifact_id else None

        if artifact_str is None:
            return False

        reverse_call = (callee, caller, artifact_str)
        if reverse_call in self._active_calls:
            return True

        session_completed = self._completed_calls.get(str(self._session_id), set()) if self._session_id else set()
        if reverse_call in session_completed:
            return True

        for active_caller, active_callee, active_artifact in self._active_calls:
            if active_artifact == artifact_str:
                if (active_caller == callee and active_callee == caller) or (
                    active_caller == caller and active_callee == callee
                ):
                    return True

        return False

    def is_arbiter_rechallenge(
        self, caller: str, call_type: InterAgentCallType
    ) -> bool:
        """Check if this is an invalid re-challenge to Arbiter."""
        if call_type == InterAgentCallType.CHALLENGE:
            session_challenges = self._arbiter_challenges.get(str(self._session_id), set()) if self._session_id else set()
            return caller in session_challenges
        return False

    async def dispatch(
        self,
        call: InterAgentCall,
        callee_agent: Any,
        custody_logger: Any,
    ) -> dict[str, Any]:
        """
        Dispatch an inter-agent call.

        Args:
            call: The inter-agent call to dispatch
            callee_agent: The agent being called
            custody_logger: Logger for custody chain entries

        Returns:
            The response from the callee agent

        Raises:
            PermittedCallViolationError: If call path is not permitted
            CircularCallError: If circular dependency detected
            ArbiterRechallengeError: If agent attempts to re-challenge Arbiter
        """
        artifact_str = str(call.artifact_id) if call.artifact_id else None

        if not self.is_call_permitted(call.caller_agent_id, call.callee_agent_id):
            raise PermittedCallViolationError(
                call.caller_agent_id, call.callee_agent_id
            )

        # Atomically check circular dependency + arbiter re-challenge + register active call
        # under a single lock to prevent TOCTOU races between concurrent coroutines.
        async with self._dispatch_lock:
            if self.is_circular_call(
                call.caller_agent_id, call.callee_agent_id, call.artifact_id
            ):
                raise CircularCallError(
                    call.caller_agent_id, call.callee_agent_id, call.artifact_id
                )

            if call.call_type == InterAgentCallType.CHALLENGE:
                sid_str = str(self._session_id)
                session_challenges = self._arbiter_challenges.setdefault(sid_str, set())
                if call.callee_agent_id in session_challenges:
                    raise ArbiterRechallengeError(call.caller_agent_id)
                session_challenges.add(call.callee_agent_id)

            self._active_calls.add(
                (call.caller_agent_id, call.callee_agent_id, artifact_str)
            )

        try:
            # 5. Log INTER_AGENT_CALL to caller's custody chain
            from core.custody_logger import EntryType

            if custody_logger:
                await custody_logger.log_entry(
                    entry_type=EntryType.INTER_AGENT_CALL,
                    agent_id=call.caller_agent_id,
                    session_id=self._session_id,  # Use actual session_id
                    content={
                        "call_id": str(call.call_id),
                        "direction": "OUTGOING",
                        "callee_agent_id": call.callee_agent_id,
                        "call_type": call.call_type.value,
                        "artifact_id": str(call.artifact_id)
                        if call.artifact_id
                        else None,
                        "payload": call.payload,
                    },
                )

            # 6. Log INTER_AGENT_CALL to callee's custody chain
            if custody_logger:
                await custody_logger.log_entry(
                    entry_type=EntryType.INTER_AGENT_CALL,
                    agent_id=call.callee_agent_id,
                    session_id=self._session_id,  # Use actual session_id
                    content={
                        "call_id": str(call.call_id),
                        "direction": "INCOMING",
                        "caller_agent_id": call.caller_agent_id,
                        "call_type": call.call_type.value,
                        "artifact_id": str(call.artifact_id)
                        if call.artifact_id
                        else None,
                        "payload": call.payload,
                    },
                )

            # 7. Invoke callee's handle_inter_agent_call method
            response = await callee_agent.handle_inter_agent_call(call)

            # 8. Update call status
            call.response = response
            call.status = "COMPLETE"
            call.completed_utc = datetime.now(UTC)

            # 9. Track completed call for circular detection (session-scoped)
            sid_str = str(self._session_id)
            self._completed_calls.setdefault(sid_str, set()).add(
                (call.caller_agent_id, call.callee_agent_id, artifact_str)
            )

            # 10. Store in history
            self._call_history.append(call)

            return response

        except Exception as e:
            call.status = "FAILED"
            call.response = {"error": str(e)}
            self._call_history.append(call)
            raise

        finally:
            # 10. Remove from active calls
            self._active_calls.discard(
                (call.caller_agent_id, call.callee_agent_id, artifact_str)
            )

    async def send(
        self,
        call: InterAgentCall,
        custody_logger: Any | None = None,
    ) -> dict[str, Any]:
        """
        Convenience method to send an inter-agent call.

        Reuses a registered agent instance if one was provided via
        ``register_agent()``; otherwise creates the callee on-demand.

        Args:
            call: The inter-agent call to send
            custody_logger: Logger for custody chain entries

        Returns:
            The response from the callee agent

        Raises:
            PermittedCallViolationError: If call path is not permitted
            CircularCallError: If circular dependency detected
            ValueError: If bus was not initialized with required components
        """
        callee_agent = self._registered_agents.get(call.callee_agent_id)

        if callee_agent is None:
            if self._config is None or self._evidence_artifact is None:
                raise ValueError(
                    "InterAgentBus not properly initialized. "
                    "Need config, evidence_artifact, and other components to send calls."
                )
            callee_agent = self._create_agent(call.callee_agent_id)

        return await self.dispatch(call, callee_agent, custody_logger)

    def _create_agent(self, agent_id: str) -> Any:
        """
        Create an agent instance for the given agent ID using the registry.
        """
        agent_class = get_agent_registry().get_agent_class(agent_id)

        # Build kwargs - only add inter_agent_bus for agents that need it
        kwargs = {
            "agent_id": agent_id,
            "session_id": self._session_id,
            "evidence_artifact": self._evidence_artifact,
            "config": self._config,
            "working_memory": self._working_memory,
            "episodic_memory": self._episodic_memory,
            "custody_logger": self._custody_logger,
            "evidence_store": self._evidence_store,
        }

        # Add inter_agent_bus for Agent2, Agent3, Agent4
        if agent_id in ("Agent2", "Agent3", "Agent4"):
            kwargs["inter_agent_bus"] = self

        return agent_class(**kwargs)

    def get_active_calls(self) -> list[tuple[str, str, str | None]]:
        """Get list of currently active calls."""
        return list(self._active_calls)

    def get_call_history(self) -> list[InterAgentCall]:
        """Get call history for audit."""
        return list(self._call_history)

    def clear_arbiter_challenges(self, session_id: str | None = None) -> None:
        """Clear arbiter challenge tracking. If session_id given, only that session; else all."""
        if session_id:
            self._arbiter_challenges.pop(str(session_id), None)
        else:
            self._arbiter_challenges.clear()

    def reset(self) -> None:
        """Reset bus state (for new sessions)."""
        self._active_calls.clear()
        self._arbiter_challenges.clear()
        self._call_history.clear()
        self._completed_calls.clear()
        self._registered_agents.clear()
