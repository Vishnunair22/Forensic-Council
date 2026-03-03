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

from core.exceptions import ForensicCouncilBaseException


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
            "completed_utc": self.completed_utc.isoformat() if self.completed_utc else None,
        }


# Permitted call paths - defines which agents can call which
PERMITTED_CALL_PATHS: dict[str, list[str]] = {
    "Agent2_Audio": ["Agent4_Video"],
    "Agent4_Video": ["Agent2_Audio"],
    "Agent3_Object": ["Agent1_ImageIntegrity"],
    "Arbiter": ["Agent1_ImageIntegrity", "Agent2_Audio", "Agent3_Object", "Agent4_Video", "Agent5_Metadata"],
}

# Agents that cannot initiate calls (can only receive)
CALL_RECEIVERS_ONLY = ["Agent1_ImageIntegrity", "Agent5_Metadata"]


class PermittedCallViolationError(ForensicCouncilBaseException):
    """Raised when an agent attempts to call another agent outside permitted paths."""
    
    def __init__(self, caller: str, callee: str):
        self.caller = caller
        self.callee = callee
        super().__init__(
            f"Call path not permitted: {caller} -> {callee}. "
            f"Permitted callees for {caller}: {PERMITTED_CALL_PATHS.get(caller, [])}"
        )


class CircularCallError(ForensicCouncilBaseException):
    """Raised when a circular call dependency is detected."""
    
    def __init__(self, caller: str, callee: str, artifact_id: Optional[UUID]):
        self.caller = caller
        self.callee = callee
        self.artifact_id = artifact_id
        super().__init__(
            f"Circular call detected: {caller} -> {callee} on artifact {artifact_id}. "
            f"Callee cannot re-initiate call to caller on same artifact within same loop."
        )


class ArbiterRechallengeError(ForensicCouncilBaseException):
    """Raised when an agent attempts to re-challenge an Arbiter challenge."""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        super().__init__(
            f"Arbiter challenges are terminal: {agent_id} cannot re-challenge the Arbiter."
        )


class InterAgentBus:
    """
    Inter-agent communication bus with anti-circular dependency enforcement.
    
    Manages calls between agents, ensuring permitted paths and preventing
    circular dependencies.
    """
    
    def __init__(self):
        # Track active calls: (caller, callee, artifact_id) tuples
        self._active_calls: set[tuple[str, str, Optional[str]]] = set()
        # Track arbiter challenges: agent_id that have been challenged
        self._arbiter_challenges: set[str] = set()
        # Track completed calls on same artifact to detect circular patterns
        self._completed_calls: list[tuple[str, str, Optional[str]]] = []
        # Call history for audit
        self._call_history: list[InterAgentCall] = []
    
    def is_call_permitted(self, caller: str, callee: str) -> bool:
        """Check if a call path is permitted."""
        permitted_callees = PERMITTED_CALL_PATHS.get(caller, [])
        return callee in permitted_callees
    
    def is_circular_call(
        self, 
        caller: str, 
        callee: str, 
        artifact_id: Optional[UUID]
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
                if (active_caller == callee and active_callee == caller) or \
                   (active_caller == caller and active_callee == callee):
                    return True
        
        return False
    
    def is_arbiter_rechallenge(self, caller: str, call_type: InterAgentCallType) -> bool:
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
        caller = call.caller_agent_id
        callee = call.callee_agent_id  # Fixed: was incorrectly using caller_agent_id
        artifact_str = str(call.artifact_id) if call.artifact_id else None
        
        # 1. Validate call path is permitted
        if not self.is_call_permitted(call.caller_agent_id, call.callee_agent_id):
            raise PermittedCallViolationError(call.caller_agent_id, call.callee_agent_id)
        
        # 2. Validate no circular dependency
        if self.is_circular_call(call.caller_agent_id, call.callee_agent_id, call.artifact_id):
            raise CircularCallError(call.caller_agent_id, call.callee_agent_id, call.artifact_id)
        
        # 3. Check for arbiter re-challenge
        if call.call_type == InterAgentCallType.CHALLENGE:
            # Track who was challenged (the callee)
            self._arbiter_challenges.add(call.callee_agent_id)
            # Check if caller was previously challenged by arbiter (cannot issue new challenges)
            if call.caller_agent_id in self._arbiter_challenges:
                raise ArbiterRechallengeError(call.caller_agent_id)
        
        # 4. Register active call
        self._active_calls.add((call.caller_agent_id, call.callee_agent_id, artifact_str))
        
        try:
            # 5. Log INTER_AGENT_CALL to caller's custody chain
            from core.custody_logger import EntryType
            await custody_logger.log_entry(
                entry_type=EntryType.INTER_AGENT_CALL,
                agent_id=call.caller_agent_id,
                session_id=call.call_id,  # Use call_id as session reference
                content={
                    "call_id": str(call.call_id),
                    "direction": "OUTGOING",
                    "callee_agent_id": call.callee_agent_id,
                    "call_type": call.call_type.value,
                    "artifact_id": str(call.artifact_id) if call.artifact_id else None,
                    "payload": call.payload,
                },
            )
            
            # 6. Log INTER_AGENT_CALL to callee's custody chain
            await custody_logger.log_entry(
                entry_type=EntryType.INTER_AGENT_CALL,
                agent_id=call.callee_agent_id,
                session_id=call.call_id,
                content={
                    "call_id": str(call.call_id),
                    "direction": "INCOMING",
                    "caller_agent_id": call.caller_agent_id,
                    "call_type": call.call_type.value,
                    "artifact_id": str(call.artifact_id) if call.artifact_id else None,
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
            self._completed_calls.append((call.caller_agent_id, call.callee_agent_id, artifact_str))
            
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
            self._active_calls.discard((call.caller_agent_id, call.callee_agent_id, artifact_str))
    
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
