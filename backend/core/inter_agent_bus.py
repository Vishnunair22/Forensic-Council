"""
Inter-Agent Communication Protocol
==================================

Implements the inter-agent communication protocol with anti-circular dependency enforcement.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.exceptions import (
    PermittedCallViolationError,
    CircularCallError,
    ArbiterRechallengeError,
)


class InterAgentCallType(str, Enum):
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
    artifact_id: Optional[UUID] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    response: Optional[dict[str, Any]] = None
    status: Literal["PENDING", "COMPLETE", "FAILED"] = "PENDING"
    created_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_utc: Optional[datetime] = None

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


# Permitted call paths - defines which agents can call which
PERMITTED_CALL_PATHS: dict[str, list[str]] = {
    "Agent2": ["Agent4"],
    "Agent4": ["Agent2"],
    "Agent3": ["Agent1"],
    "Arbiter": ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"],
}

# Agents that cannot initiate calls (can only receive)
CALL_RECEIVERS_ONLY = ["Agent1", "Agent5"]


class InterAgentBus:
    """
    Inter-agent communication bus with anti-circular dependency enforcement.

    Manages calls between agents, ensuring permitted paths and preventing
    circular dependencies.
    """

    def __init__(
        self,
        config: Optional[Any] = None,
        evidence_artifact: Optional[Any] = None,
        session_id: Optional[UUID] = None,
        working_memory: Optional[Any] = None,
        episodic_memory: Optional[Any] = None,
        custody_logger: Optional[Any] = None,
        evidence_store: Optional[Any] = None,
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
        self._active_calls: set[tuple[str, str, Optional[str]]] = set()
        # Track arbiter challenges: agent_id that have been challenged
        self._arbiter_challenges: set[str] = set()
        # Track completed calls on same artifact to detect circular patterns
        self._completed_calls: set[tuple[str, str, Optional[str]]] = set()
        # Call history for audit
        self._call_history: list[InterAgentCall] = []

    def is_call_permitted(self, caller: str, callee: str) -> bool:
        """Check if a call path is permitted."""
        permitted_callees = PERMITTED_CALL_PATHS.get(caller, [])
        return callee in permitted_callees

    def is_circular_call(
        self, caller: str, callee: str, artifact_id: Optional[UUID]
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

        # If no artifact_id, don't check for circular calls
        if artifact_str is None:
            return False

        # Check if callee has an active call to caller on same artifact
        reverse_call = (callee, caller, artifact_str)
        if reverse_call in self._active_calls:
            return True

        # Check if callee has completed a call to caller on same artifact (circular)
        if reverse_call in self._completed_calls:
            return True

        # Check for any active call involving these agents on same artifact
        for active_caller, active_callee, active_artifact in self._active_calls:
            if active_artifact == artifact_str:
                # If there's already a call chain involving these agents
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
            return caller in self._arbiter_challenges
        return False

    async def dispatch(
        self,
        call: InterAgentCall,
        callee_agent: Any,  # ForensicAgent - avoiding circular import
        custody_logger: Any,  # CustodyLogger - avoiding circular import
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

        # 1. Validate call path is permitted
        if not self.is_call_permitted(call.caller_agent_id, call.callee_agent_id):
            raise PermittedCallViolationError(
                call.caller_agent_id, call.callee_agent_id
            )

        # 2. Validate no circular dependency
        if self.is_circular_call(
            call.caller_agent_id, call.callee_agent_id, call.artifact_id
        ):
            raise CircularCallError(
                call.caller_agent_id, call.callee_agent_id, call.artifact_id
            )

        # 3. Check for arbiter re-challenge
        if call.call_type == InterAgentCallType.CHALLENGE:
            # Track who was challenged (the callee)
            self._arbiter_challenges.add(call.callee_agent_id)
            # Check if caller was previously challenged by arbiter (cannot issue new challenges)
            if call.caller_agent_id in self._arbiter_challenges:
                raise ArbiterRechallengeError(call.caller_agent_id)

        # 4. Register active call
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
            call.completed_utc = datetime.now(timezone.utc)

            # 9. Track completed call for circular detection
            self._completed_calls.add(
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
        custody_logger: Optional[Any] = None,
    ) -> dict[str, Any]:
        """
        Convenience method to send an inter-agent call.

        Creates the callee agent on-demand and dispatches the call.

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
        if self._config is None or self._evidence_artifact is None:
            raise ValueError(
                "InterAgentBus not properly initialized. "
                "Need config, evidence_artifact, and other components to send calls."
            )

        # Create the callee agent
        callee_agent = self._create_agent(call.callee_agent_id)

        # Dispatch the call
        return await self.dispatch(call, callee_agent, custody_logger)

    def _create_agent(self, agent_id: str) -> Any:
        """
        Create an agent instance for the given agent ID.

        Args:
            agent_id: ID of the agent to create (Agent1-5)

        Returns:
            An instance of the requested agent

        Raises:
            ValueError: If agent_id is not recognized
        """
        from agents.agent1_image import Agent1Image
        from agents.agent2_audio import Agent2Audio
        from agents.agent3_object import Agent3Object
        from agents.agent4_video import Agent4Video
        from agents.agent5_metadata import Agent5Metadata

        agent_classes = {
            "Agent1": Agent1Image,
            "Agent2": Agent2Audio,
            "Agent3": Agent3Object,
            "Agent4": Agent4Video,
            "Agent5": Agent5Metadata,
        }

        if agent_id not in agent_classes:
            raise ValueError(
                f"Unknown agent_id: {agent_id}. Must be one of {list(agent_classes.keys())}"
            )

        agent_class = agent_classes[agent_id]

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

    def get_active_calls(self) -> list[tuple[str, str, Optional[str]]]:
        """Get list of currently active calls."""
        return list(self._active_calls)

    def get_call_history(self) -> list[InterAgentCall]:
        """Get call history for audit."""
        return list(self._call_history)

    def clear_arbiter_challenges(self) -> None:
        """Clear arbiter challenge tracking (for new sessions)."""
        self._arbiter_challenges.clear()

    def reset(self) -> None:
        """Reset bus state (for new sessions)."""
        self._active_calls.clear()
        self._arbiter_challenges.clear()
        self._call_history.clear()
        self._completed_calls.clear()
