"""
Tests for Inter-Agent Communication Protocol
=============================================

Tests the inter-agent bus with anti-circular dependency enforcement.
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from core.inter_agent_bus import (
    InterAgentBus,
    InterAgentCall,
    InterAgentCallType,
    PERMITTED_CALL_PATHS,
    PermittedCallViolationError,
    CircularCallError,
    ArbiterRechallengeError,
)


class TestPermittedCallPaths:
    """Test permitted call path definitions."""

    def test_agent2_can_call_agent4(self):
        """Agent2_Audio can call Agent4_Video."""
        assert "Agent4_Video" in PERMITTED_CALL_PATHS.get("Agent2_Audio", [])

    def test_agent4_can_call_agent2(self):
        """Agent4_Video can call Agent2_Audio."""
        assert "Agent2_Audio" in PERMITTED_CALL_PATHS.get("Agent4_Video", [])

    def test_agent3_can_call_agent1(self):
        """Agent3_Object can call Agent1_ImageIntegrity."""
        assert "Agent1_ImageIntegrity" in PERMITTED_CALL_PATHS.get("Agent3_Object", [])

    def test_arbiter_can_call_all_agents(self):
        """Arbiter can call all agents."""
        expected = ["Agent1_ImageIntegrity", "Agent2_Audio", "Agent3_Object", "Agent4_Video", "Agent5_Metadata"]
        for agent in expected:
            assert agent in PERMITTED_CALL_PATHS.get("Arbiter", [])


class TestInterAgentBus:
    """Test InterAgentBus functionality."""

    @pytest.fixture
    def bus(self):
        """Create a fresh InterAgentBus."""
        return InterAgentBus()

    @pytest.fixture
    def mock_custody_logger(self):
        """Create a mock custody logger."""
        logger = AsyncMock()
        logger.log_entry = AsyncMock(return_value=uuid4())
        return logger

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent with handle_inter_agent_call."""
        agent = AsyncMock()
        agent.handle_inter_agent_call = AsyncMock(return_value={"status": "success", "finding": "test"})
        return agent

    @pytest.mark.asyncio
    async def test_permitted_call_agent2_to_agent4_succeeds(self, bus, mock_custody_logger, mock_agent):
        """Test that Agent2_Audio can call Agent4_Video."""
        call = InterAgentCall(
            caller_agent_id="Agent2_Audio",
            callee_agent_id="Agent4_Video",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=uuid4(),
            payload={"question": "Verify timestamp sync"},
        )
        
        response = await bus.dispatch(call, mock_agent, mock_custody_logger)
        
        assert response["status"] == "success"
        assert mock_agent.handle_inter_agent_call.called

    @pytest.mark.asyncio
    async def test_permitted_call_agent4_to_agent2_succeeds(self, bus, mock_custody_logger, mock_agent):
        """Test that Agent4_Video can call Agent2_Audio."""
        call = InterAgentCall(
            caller_agent_id="Agent4_Video",
            callee_agent_id="Agent2_Audio",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=uuid4(),
            payload={"context_finding": {"frame": 100}},
        )
        
        response = await bus.dispatch(call, mock_agent, mock_custody_logger)
        
        assert response["status"] == "success"

    @pytest.mark.asyncio
    async def test_permitted_call_agent3_to_agent1_succeeds(self, bus, mock_custody_logger, mock_agent):
        """Test that Agent3_Object can call Agent1_ImageIntegrity."""
        call = InterAgentCall(
            caller_agent_id="Agent3_Object",
            callee_agent_id="Agent1_ImageIntegrity",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=uuid4(),
            payload={"region_ref": {"x": 0, "y": 0, "w": 100, "h": 100}},
        )
        
        response = await bus.dispatch(call, mock_agent, mock_custody_logger)
        
        assert response["status"] == "success"

    @pytest.mark.asyncio
    async def test_unpermitted_call_agent1_to_agent3_raises_error(self, bus, mock_custody_logger, mock_agent):
        """Test that Agent1 cannot call Agent3 (not in permitted paths)."""
        call = InterAgentCall(
            caller_agent_id="Agent1_ImageIntegrity",
            callee_agent_id="Agent3_Object",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=uuid4(),
            payload={},
        )
        
        with pytest.raises(PermittedCallViolationError) as exc_info:
            await bus.dispatch(call, mock_agent, mock_custody_logger)
        
        assert "Agent1_ImageIntegrity" in str(exc_info.value)
        assert "Agent3_Object" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unpermitted_call_agent1_to_agent2_raises_error(self, bus, mock_custody_logger, mock_agent):
        """Test that Agent1 cannot call Agent2 (not in permitted paths)."""
        call = InterAgentCall(
            caller_agent_id="Agent1_ImageIntegrity",
            callee_agent_id="Agent2_Audio",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=uuid4(),
            payload={},
        )
        
        with pytest.raises(PermittedCallViolationError):
            await bus.dispatch(call, mock_agent, mock_custody_logger)

    @pytest.mark.asyncio
    async def test_circular_call_detected_and_blocked(self, bus, mock_custody_logger, mock_agent):
        """Test that circular calls are detected and blocked."""
        artifact_id = uuid4()
        
        # First call: Agent2 -> Agent4
        call1 = InterAgentCall(
            caller_agent_id="Agent2_Audio",
            callee_agent_id="Agent4_Video",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=artifact_id,
            payload={},
        )
        await bus.dispatch(call1, mock_agent, mock_custody_logger)
        
        # Reset the mock to clear the first call
        mock_agent.handle_inter_agent_call.reset_mock()
        
        # Second call: Agent4 -> Agent2 on SAME artifact (circular!)
        call2 = InterAgentCall(
            caller_agent_id="Agent4_Video",
            callee_agent_id="Agent2_Audio",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=artifact_id,
            payload={},
        )
        
        with pytest.raises(CircularCallError) as exc_info:
            await bus.dispatch(call2, mock_agent, mock_custody_logger)
        
        assert "Agent4_Video" in str(exc_info.value)
        assert "Agent2_Audio" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_inter_agent_call_logged_to_both_custody_chains(self, bus, mock_custody_logger, mock_agent):
        """Test that inter-agent call is logged to both caller and callee custody chains."""
        call = InterAgentCall(
            caller_agent_id="Agent2_Audio",
            callee_agent_id="Agent4_Video",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=uuid4(),
            payload={"test": "data"},
        )
        
        await bus.dispatch(call, mock_agent, mock_custody_logger)
        
        # Verify log_entry was called twice (once for caller, once for callee)
        assert mock_custody_logger.log_entry.call_count == 2
        
        # Check first call (caller's outgoing)
        first_call_content = mock_custody_logger.log_entry.call_args_list[0][1]["content"]
        assert first_call_content["direction"] == "OUTGOING"
        assert first_call_content["callee_agent_id"] == "Agent4_Video"
        
        # Check second call (callee's incoming)
        second_call_content = mock_custody_logger.log_entry.call_args_list[1][1]["content"]
        assert second_call_content["direction"] == "INCOMING"
        assert second_call_content["caller_agent_id"] == "Agent2_Audio"

    @pytest.mark.asyncio
    async def test_arbiter_challenge_call_permitted_to_all_agents(self, bus, mock_custody_logger, mock_agent):
        """Test that Arbiter can challenge any agent."""
        agents = ["Agent1_ImageIntegrity", "Agent2_Audio", "Agent3_Object", "Agent4_Video", "Agent5_Metadata"]
        
        for agent_id in agents:
            call = InterAgentCall(
                caller_agent_id="Arbiter",
                callee_agent_id=agent_id,
                call_type=InterAgentCallType.CHALLENGE,
                artifact_id=uuid4(),
                payload={"challenge_reason": "inconsistent_finding"},
            )
            
            response = await bus.dispatch(call, mock_agent, mock_custody_logger)
            assert response["status"] == "success"
            bus.reset()  # Reset for next iteration

    @pytest.mark.asyncio
    async def test_arbiter_challenge_cannot_be_re_challenged(self, bus, mock_custody_logger, mock_agent):
        """Test that an agent challenged by Arbiter cannot issue a CHALLENGE call."""
        artifact_id = uuid4()
        
        # First: Arbiter challenges Agent2
        call1 = InterAgentCall(
            caller_agent_id="Arbiter",
            callee_agent_id="Agent2_Audio",
            call_type=InterAgentCallType.CHALLENGE,
            artifact_id=artifact_id,
            payload={},
        )
        await bus.dispatch(call1, mock_agent, mock_custody_logger)
        
        # Reset mock
        mock_agent.handle_inter_agent_call.reset_mock()
        mock_custody_logger.log_entry.reset_mock()
        
        # Second: Agent2 tries to issue CHALLENGE call to Agent4 (should fail)
        call2 = InterAgentCall(
            caller_agent_id="Agent2_Audio",
            callee_agent_id="Agent4_Video",
            call_type=InterAgentCallType.CHALLENGE,
            artifact_id=artifact_id,
            payload={},
        )
        
        with pytest.raises(ArbiterRechallengeError) as exc_info:
            await bus.dispatch(call2, mock_agent, mock_custody_logger)
        
        assert "Arbiter" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_without_artifact_allows_bidirectional(self, bus, mock_custody_logger, mock_agent):
        """Test that calls without artifact_id don't trigger circular detection."""
        # First call without artifact
        call1 = InterAgentCall(
            caller_agent_id="Agent2_Audio",
            callee_agent_id="Agent4_Video",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=None,
            payload={},
        )
        await bus.dispatch(call1, mock_agent, mock_custody_logger)
        
        mock_agent.handle_inter_agent_call.reset_mock()
        
        # Second call without artifact should succeed (no artifact means no circle)
        call2 = InterAgentCall(
            caller_agent_id="Agent4_Video",
            callee_agent_id="Agent2_Audio",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=None,
            payload={},
        )
        
        # Should not raise
        response = await bus.dispatch(call2, mock_agent, mock_custody_logger)
        assert response["status"] == "success"

    @pytest.mark.asyncio
    async def test_bus_tracks_active_calls(self, bus, mock_custody_logger, mock_agent):
        """Test that bus tracks active calls."""
        artifact_id = uuid4()
        
        call = InterAgentCall(
            caller_agent_id="Agent2_Audio",
            callee_agent_id="Agent4_Video",
            call_type=InterAgentCallType.COLLABORATIVE,
            artifact_id=artifact_id,
            payload={},
        )
        
        # Before dispatch
        assert len(bus.get_active_calls()) == 0
        
        await bus.dispatch(call, mock_agent, mock_custody_logger)
        
        # After dispatch - should be cleared in finally block
        assert len(bus.get_active_calls()) == 0
        
        # But should be in history
        assert len(bus.get_call_history()) == 1

    @pytest.mark.asyncio
    async def test_bus_reset_clears_state(self, bus):
        """Test that reset clears all state."""
        bus._active_calls.add(("test", "test", "test"))
        bus._arbiter_challenges.add("test_agent")
        
        bus.reset()
        
        assert len(bus._active_calls) == 0
        assert len(bus._arbiter_challenges) == 0
        assert len(bus._call_history) == 0
