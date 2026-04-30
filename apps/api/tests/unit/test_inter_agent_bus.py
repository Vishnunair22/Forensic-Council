"""
Unit tests for the InterAgentBus protocol.

Covers:
- Permitted call paths (via AgentRegistry)
- Receiver-only agents (empty permitted_callees)
- Circular call detection
- Arbiter rechallenge prevention
- InterAgentCall model serialization
- call_history audit trail
- PermittedCallViolationError, CircularCallError, ArbiterRechallengeError
"""

import os
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.agent_registry import get_agent_registry
from core.exceptions import (
    ArbiterRechallengeError,
    CircularCallError,
    PermittedCallViolationError,
)
from core.inter_agent_bus import (
    InterAgentBus,
    InterAgentCall,
    InterAgentCallType,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _bus(session_id=None) -> InterAgentBus:
    return InterAgentBus(session_id=session_id)


def _call(
    caller: str,
    callee: str,
    call_type: InterAgentCallType = InterAgentCallType.COLLABORATIVE,
    artifact_id: UUID | None = None,
) -> InterAgentCall:
    return InterAgentCall(
        caller_agent_id=caller,
        callee_agent_id=callee,
        call_type=call_type,
        artifact_id=artifact_id,
    )


# ── PERMITTED call paths (via registry) ──────────────────────────────────────


class TestPermittedCallPaths:
    def test_agent2_can_call_agent4(self):
        b = _bus()
        assert b.is_call_permitted("Agent2", "Agent4")

    def test_agent4_can_call_agent2(self):
        b = _bus()
        assert b.is_call_permitted("Agent4", "Agent2")

    def test_agent3_can_call_agent1(self):
        b = _bus()
        assert b.is_call_permitted("Agent3", "Agent1")

    def test_arbiter_can_call_all_agents(self):
        b = _bus()
        for agent in ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]:
            assert b.is_call_permitted("Arbiter", agent), f"Arbiter→{agent} should be permitted"

    def test_agent1_cannot_call_agent2(self):
        b = _bus()
        assert not b.is_call_permitted("Agent1", "Agent2")

    def test_agent5_cannot_call_agent3(self):
        b = _bus()
        assert not b.is_call_permitted("Agent5", "Agent3")

    def test_agent2_cannot_call_agent1(self):
        b = _bus()
        assert not b.is_call_permitted("Agent2", "Agent1")

    def test_unknown_caller_has_no_permissions(self):
        b = _bus()
        assert not b.is_call_permitted("UnknownAgent", "Agent1")


# ── Receiver-only agents (empty permitted_callees in registry) ─────────────


class TestCallReceiversOnly:
    def test_agent5_has_no_permitted_callees(self):
        reg = get_agent_registry()
        assert reg.get_permitted_callees("Agent5") == []

    def test_agent5_cannot_initiate_calls(self):
        b = _bus()
        assert not b.is_call_permitted("Agent5", "Agent1")
        assert not b.is_call_permitted("Agent5", "Agent2")
        assert not b.is_call_permitted("Agent5", "Agent3")
        assert not b.is_call_permitted("Agent5", "Agent4")

    def test_agent1_has_permitted_callees(self):
        reg = get_agent_registry()
        assert len(reg.get_permitted_callees("Agent1")) > 0

    def test_agent2_has_permitted_callees(self):
        reg = get_agent_registry()
        assert len(reg.get_permitted_callees("Agent2")) > 0

    def test_arbiter_can_call_all_registered_agents(self):
        reg = get_agent_registry()
        all_agents = reg.get_all_agent_ids()
        for agent in all_agents:
            assert (
                agent in reg.get_permitted_callees("Arbiter")
                or reg.get_permitted_callees("Arbiter") == all_agents
            )


# ── Circular call detection ──────────────────────────────────────────────────


class TestCircularCallDetection:
    def test_no_circular_without_artifact_id(self):
        b = _bus()
        assert not b.is_circular_call("Agent2", "Agent4", artifact_id=None)

    def test_no_circular_on_fresh_bus(self):
        b = _bus()
        artifact = uuid4()
        assert not b.is_circular_call("Agent2", "Agent4", artifact_id=artifact)

    def test_circular_when_reverse_call_active(self):
        b = _bus()
        artifact = uuid4()
        artifact_str = str(artifact)
        # Simulate Agent4 has an active call to Agent2
        b._active_calls.add(("Agent4", "Agent2", artifact_str))
        # Now Agent2 calling Agent4 is circular
        assert b.is_circular_call("Agent2", "Agent4", artifact_id=artifact)

    def test_circular_when_reverse_call_completed(self):
        session_id = uuid4()
        b = _bus(session_id=session_id)
        artifact = uuid4()
        artifact_str = str(artifact)
        # Simulate Agent4 has completed a call to Agent2 in this session
        session_str = str(session_id)
        b._completed_calls[session_str] = {("Agent4", "Agent2", artifact_str)}
        assert b.is_circular_call("Agent2", "Agent4", artifact_id=artifact)

    def test_not_circular_for_different_artifact(self):
        b = _bus()
        artifact_a = uuid4()
        artifact_b = uuid4()
        b._active_calls.add(("Agent4", "Agent2", str(artifact_a)))
        # Different artifact: not circular
        assert not b.is_circular_call("Agent2", "Agent4", artifact_id=artifact_b)

    def test_not_circular_for_no_session_on_completed_calls(self):
        """Without session_id, completed_calls check is skipped."""
        b = _bus(session_id=None)
        artifact = uuid4()
        artifact_str = str(artifact)
        # Even with data in _completed_calls, no session = no check
        b._completed_calls["None"] = {("Agent4", "Agent2", artifact_str)}
        # Active calls check still works
        assert not b.is_circular_call("Agent2", "Agent4", artifact_id=artifact)


# ── Arbiter rechallenge detection ────────────────────────────────────────────


class TestArbiterRechallenge:
    def test_no_rechallenge_on_fresh_bus(self):
        session_id = uuid4()
        b = _bus(session_id=session_id)
        assert not b.is_arbiter_rechallenge("Agent1", InterAgentCallType.CHALLENGE)

    def test_rechallenge_detected_after_challenge(self):
        session_id = uuid4()
        b = _bus(session_id=session_id)
        session_str = str(session_id)
        # Mark Agent1 as having been challenged already
        b._arbiter_challenges[session_str] = {"Agent1"}
        assert b.is_arbiter_rechallenge("Agent1", InterAgentCallType.CHALLENGE)

    def test_collaborative_call_never_rechallenge(self):
        session_id = uuid4()
        b = _bus(session_id=session_id)
        session_str = str(session_id)
        b._arbiter_challenges[session_str] = {"Agent1"}
        assert not b.is_arbiter_rechallenge("Agent1", InterAgentCallType.COLLABORATIVE)

    def test_different_agent_not_rechallenge(self):
        session_id = uuid4()
        b = _bus(session_id=session_id)
        session_str = str(session_id)
        b._arbiter_challenges[session_str] = {"Agent1"}
        assert not b.is_arbiter_rechallenge("Agent2", InterAgentCallType.CHALLENGE)

    def test_no_rechallenge_without_session_id(self):
        """Bus with no session_id never detects rechallenge (safe default)."""
        b = _bus(session_id=None)
        b._arbiter_challenges["None"] = {"Agent1"}
        # is_arbiter_rechallenge returns empty set when session_id is None
        assert not b.is_arbiter_rechallenge("Agent1", InterAgentCallType.CHALLENGE)


# ── InterAgentCall model ──────────────────────────────────────────────────────


class TestInterAgentCallModel:
    def test_call_has_unique_id(self):
        c1 = _call("Agent2", "Agent4")
        c2 = _call("Agent2", "Agent4")
        assert c1.call_id != c2.call_id

    def test_default_status_is_pending(self):
        c = _call("Agent2", "Agent4")
        assert c.status == "PENDING"

    def test_to_dict_contains_required_keys(self):
        c = _call("Agent2", "Agent4", artifact_id=uuid4())
        d = c.to_dict()
        assert "call_id" in d
        assert "caller_agent_id" in d
        assert "callee_agent_id" in d
        assert "call_type" in d
        assert "status" in d
        assert "created_utc" in d

    def test_to_dict_artifact_id_string(self):
        artifact = uuid4()
        c = _call("Agent2", "Agent4", artifact_id=artifact)
        d = c.to_dict()
        assert d["artifact_id"] == str(artifact)

    def test_to_dict_no_artifact_id_is_none(self):
        c = _call("Agent2", "Agent4")
        d = c.to_dict()
        assert d["artifact_id"] is None

    def test_call_type_value_in_dict(self):
        c = _call("Arbiter", "Agent1", call_type=InterAgentCallType.CHALLENGE)
        d = c.to_dict()
        assert d["call_type"] == "CHALLENGE"


# ── dispatch validation (permission errors) ────────────────────────────────────


class TestDispatchPermissions:
    @pytest.mark.asyncio
    async def test_dispatch_unpermitted_path_raises(self):
        b = _bus()
        bad_call = _call("Agent1", "Agent2")  # Agent1 → Agent2 not permitted
        from unittest.mock import AsyncMock, MagicMock

        mock_callee = MagicMock()
        mock_logger = AsyncMock()
        with pytest.raises(PermittedCallViolationError):
            await b.dispatch(bad_call, mock_callee, mock_logger)

    @pytest.mark.asyncio
    async def test_dispatch_circular_raises(self):
        b = _bus()
        artifact = uuid4()
        artifact_str = str(artifact)
        # Simulate reverse active call
        b._active_calls.add(("Agent4", "Agent2", artifact_str))
        circular_call = _call("Agent2", "Agent4", artifact_id=artifact)
        from unittest.mock import AsyncMock, MagicMock

        with pytest.raises(CircularCallError):
            await b.dispatch(circular_call, MagicMock(), AsyncMock())

    @pytest.mark.asyncio
    async def test_dispatch_arbiter_rechallenge_raises(self):
        b = _bus()
        # Pre-populate challenges: Agent1 was already challenged (stored under "None" session key)
        b._arbiter_challenges["None"] = {"Agent1"}
        rechallenge = _call("Arbiter", "Agent1", call_type=InterAgentCallType.CHALLENGE)
        from unittest.mock import AsyncMock, MagicMock

        with pytest.raises(ArbiterRechallengeError):
            await b.dispatch(rechallenge, MagicMock(), AsyncMock())
