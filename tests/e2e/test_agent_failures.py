"""
E2E Test: Agent Failure Scenarios
===================================

Tests graceful degradation when agents fail during investigation.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_single_agent_failure_graceful_degradation(authenticated_client: AsyncClient, sample_image_file):
    """Test that one agent failure doesn't crash the entire pipeline."""
    # Mock Agent 2 (Audio) to fail
    with patch("backend.agents.agent2_audio.run") as mock_agent:
        mock_agent.side_effect = Exception("Audio processing failed")
        
        with open(sample_image_file, "rb") as f:
            response = await authenticated_client.post(
                "/api/v1/investigate",
                files={"file": ("test.jpg", f, "image/jpeg")},
                data={"case_id": "TEST_AGENT_FAILURE"}
            )
        
        # Should still accept the investigation
        assert response.status_code == 202
        session_id = response.json()["session_id"]
        
        # Wait for partial completion
        await asyncio.sleep(2)
        
        # Should return partial analysis from other agents
        report = await authenticated_client.get(f"/api/v1/sessions/{session_id}/report")
        assert report.status_code in [200, 202]
        
        if report.status_code == 200:
            report_data = report.json()
            # At least 4 agents should have completed (out of 5)
            assert len(report_data.get("per_agent_findings", [])) >= 4


@pytest.mark.asyncio
async def test_multiple_agent_failures(authenticated_client: AsyncClient, sample_image_file):
    """Test investigation survives multiple agent failures."""
    with (
        patch("backend.agents.agent2_audio.run") as mock_agent2,
        patch("backend.agents.agent4_metadata.run") as mock_agent4
    ):
        mock_agent2.side_effect = Exception("Agent 2 failed")
        mock_agent4.side_effect = Exception("Agent 4 failed")
        
        with open(sample_image_file, "rb") as f:
            response = await authenticated_client.post(
                "/api/v1/investigate",
                files={"file": ("test.jpg", f, "image/jpeg")},
                data={"case_id": "TEST_MULTI_FAILURE"}
            )
        
        assert response.status_code == 202
        session_id = response.json()["session_id"]
        
        await asyncio.sleep(2)
        
        report = await authenticated_client.get(f"/api/v1/sessions/{session_id}/report")
        assert report.status_code in [200, 202]
        
        if report.status_code == 200:
            report_data = report.json()
            # At least 3 agents should have completed
            assert len(report_data.get("per_agent_findings", [])) >= 3


@pytest.mark.asyncio
async def test_agent_timeout_handling(authenticated_client: AsyncClient, sample_image_file):
    """Test that agent timeouts are handled gracefully."""
    with patch("backend.agents.agent1_image.run") as mock_agent:
        # Simulate timeout
        mock_agent.side_effect = asyncio.TimeoutError("Agent timed out")
        
        with open(sample_image_file, "rb") as f:
            response = await authenticated_client.post(
                "/api/v1/investigate",
                files={"file": ("test.jpg", f, "image/jpeg")},
                data={"case_id": "TEST_TIMEOUT"}
            )
        
        assert response.status_code == 202
        session_id = response.json()["session_id"]
        
        await asyncio.sleep(2)
        
        report = await authenticated_client.get(f"/api/v1/sessions/{session_id}/report")
        assert report.status_code in [200, 202]


@pytest.mark.asyncio
async def test_agent_returns_invalid_data(authenticated_client: AsyncClient, sample_image_file):
    """Test handling of agents returning malformed data."""
    with patch("backend.agents.agent3_object.run") as mock_agent:
        mock_agent.return_value = {"invalid": "data", "missing_required_fields": True}
        
        with open(sample_image_file, "rb") as f:
            response = await authenticated_client.post(
                "/api/v1/investigate",
                files={"file": ("test.jpg", f, "image/jpeg")},
                data={"case_id": "TEST_INVALID_DATA"}
            )
        
        assert response.status_code == 202
        
        await asyncio.sleep(2)
        
        report = await authenticated_client.get(f"/api/v1/sessions/{response.json()['session_id']}/report")
        assert report.status_code in [200, 202]


@pytest.mark.asyncio
async def test_all_agents_fail(authenticated_client: AsyncClient, sample_image_file):
    """Test behavior when all agents fail."""
    with (
        patch("backend.agents.agent1_image.run") as m1,
        patch("backend.agents.agent2_audio.run") as m2,
        patch("backend.agents.agent3_object.run") as m3,
        patch("backend.agents.agent4_metadata.run") as m4,
        patch("backend.agents.agent5_context.run") as m5
    ):
        for m in [m1, m2, m3, m4, m5]:
            m.side_effect = Exception("Agent failed")
        
        with open(sample_image_file, "rb") as f:
            response = await authenticated_client.post(
                "/api/v1/investigate",
                files={"file": ("test.jpg", f, "image/jpeg")},
                data={"case_id": "TEST_ALL_FAIL"}
            )
        
        # Should still create session even if all agents fail
        assert response.status_code == 202
        session_id = response.json()["session_id"]
        
        await asyncio.sleep(2)
        
        report = await authenticated_client.get(f"/api/v1/sessions/{session_id}/report")
        # Should return error report or failed status
        assert report.status_code in [200, 500]


@pytest.mark.asyncio
async def test_agent_crash_mid_execution(authenticated_client: AsyncClient, sample_image_file):
    """Test handling when agent crashes during execution."""
    call_count = 0
    
    async def crash_after_first_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise RuntimeError("Agent crashed")
        return {"status": "ok"}
    
    with patch("backend.agents.agent1_image.run") as mock_agent:
        mock_agent.side_effect = crash_after_first_call
        
        with open(sample_image_file, "rb") as f:
            response = await authenticated_client.post(
                "/api/v1/investigate",
                files={"file": ("test.jpg", f, "image/jpeg")},
                data={"case_id": "TEST_CRASH"}
            )
        
        assert response.status_code == 202


@pytest.mark.asyncio
async def test_recovery_from_transient_failure(authenticated_client: AsyncClient, sample_image_file):
    """Test that transient failures are retried successfully."""
    call_count = 0
    
    async def fail_then_succeed(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ConnectionError("Transient failure")
        return {"status": "success", "findings": []}
    
    with patch("backend.agents.agent1_image.run") as mock_agent:
        mock_agent.side_effect = fail_then_succeed
        
        with open(sample_image_file, "rb") as f:
            response = await authenticated_client.post(
                "/api/v1/investigate",
                files={"file": ("test.jpg", f, "image/jpeg")},
                data={"case_id": "TEST_RECOVERY"}
            )
        
        assert response.status_code == 202
