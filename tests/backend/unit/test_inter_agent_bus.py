"""
Unit tests for the InterAgentBus protocol.

Covers:
- Permitted call paths (PERMITTED_CALL_PATHS)
- Receiver-only agents cannot initiate calls
- Circular call detection
- Arbiter rechallenge prevention
- InterAgentCall model serialization
- call_history audit trail
- PermittedCallViolationError, CircularCallError, ArbiterRechallengeError
"""

import os
import pytest
from uuid import uuid4, UUID

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

from core.inter_agent_bus import (
    InterAgentBus,
    InterAgentCall,
    InterAgentCallType,
    PERMITTED_CALL_PATHS,
    CALL_RECEIVERS_ONLY,
)
from core.exceptions import (
    CircularCallError,
    PermittedCallViolationError,
    ArbiterRechallengeError,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bus() -> InterAgentBus:
    return InterAgentBus()


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


# ── PERMITTED_CALL_PATHS ──────────────────────────────────────────────────────

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


# ── CALL_RECEIVERS_ONLY ───────────────────────────────────────────────────────

class TestCallReceiversOnly:
    def test_agent1_is_receiver_only(self):
        assert "Agent1" in CALL_RECEIVERS_ONLY

    def test_agent5_is_receiver_only(self):
        assert "Agent5" in CALL_RECEIVERS_ONLY

    def test_agent2_is_not_receiver_only(self):
        assert "Agent2" not in CALL_RECEIVERS_ONLY

    def test_arbiter_is_not_receiver_only(self):
        assert "Arbiter" not in CALL_RECEIVERS_ONLY


# ── Circular call detection ───────────────────────────────────────────────────

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
        b = _bus()
        artifact = uuid4()
        artifact_str = str(artifact)
        # Simulate Agent4 has completed a call to Agent2
        b._completed_calls.add(("Agent4", "Agent2", artifact_str))
        assert b.is_circular_call("Agent2", "Agent4", artifact_id=artifact)

    def test_not_circular_for_different_artifact(self):
        b = _bus()
        artifact_a = uuid4()
        artifact_b = uuid4()
        b._active_calls.add(("Agent4", "Agent2", str(artifact_a)))
        # Different artifact: not circular
        assert not b.is_circular_call("Agent2", "Agent4", artifact_id=artifact_b)


# ── Arbiter rechallenge detection ─────────────────────────────────────────────

class TestArbiterRechallenge:
    def test_no_rechallenge_on_fresh_bus(self):
        b = _bus()
        assert not b.is_arbiter_rechallenge("Agent1", InterAgentCallType.CHALLENGE)

    def test_rechallenge_detected_after_challenge(self):
        b = _bus()
        b._arbiter_challenges.add("Agent1")
        assert b.is_arbiter_rechallenge("Agent1", InterAgentCallType.CHALLENGE)

    def test_collaborative_call_never_rechallenge(self):
        b = _bus()
        b._arbiter_challenges.add("Agent1")
        assert not b.is_arbiter_rechallenge("Agent1", InterAgentCallType.COLLABORATIVE)

    def test_different_agent_not_rechallenge(self):
        b = _bus()
        b._arbiter_challenges.add("Agent1")
        assert not b.is_arbiter_rechallenge("Agent2", InterAgentCallType.CHALLENGE)


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


# ── dispatch validation (permission errors) ───────────────────────────────────

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
        # dispatch adds callee to _arbiter_challenges, then checks if caller is in set.
        # Simulate: Arbiter itself has been marked as challenged previously.
        b._arbiter_challenges.add("Arbiter")
        rechallenge = _call("Arbiter", "Agent1", call_type=InterAgentCallType.CHALLENGE)
        from unittest.mock import AsyncMock, MagicMock
        with pytest.raises(ArbiterRechallengeError):
            await b.dispatch(rechallenge, MagicMock(), AsyncMock())
