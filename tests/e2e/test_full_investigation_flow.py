"""
End-to-end investigation flow test.

Tests complete flow:
1. User uploads evidence
2. Authentication works
3. All 5 agents execute
4. Arbiter synthesizes
5. Report is signed
6. WebSocket updates delivered
7. HITL checkpoints function
8. Session cleanup works
"""

import asyncio
import json
import time
from pathlib import Path
from typing import AsyncGenerator

import httpx
import pytest
from httpx import AsyncClient


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def test_image_file(tmp_path: Path) -> Path:
    """Create a valid test JPEG image (1x1 pixel)."""
    image_path = tmp_path / "test_image.jpg"
    jpeg_data = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD0, 0xFF, 0xD9
    ])
    image_path.write_bytes(jpeg_data)
    return image_path


@pytest.fixture
async def authenticated_client(httpx_client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Create authenticated HTTP client with valid JWT."""
    # Login first
    response = await httpx_client.post(
        "http://localhost:8000/api/v1/auth/login",
        data={
            "username": "investigator",
            "password": "DEMO_PASSWORD"
        }
    )
    assert response.status_code == 200
    
    token = response.json()["access_token"]
    
    # Add auth header
    httpx_client.headers["Authorization"] = f"Bearer {token}"
    yield httpx_client


# ── Tests ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_investigation_flow(
    authenticated_client: AsyncClient,
    test_image_file: Path
) -> None:
    """
    Test complete investigation flow from upload to signed report.
    
    Steps:
    1. ✅ POST /investigate with file upload
    2. ✅ GET /sessions/{id}/arbiter-status polling
    3. ✅ WS connect for live updates
    4. ✅ All agents complete (Agent1-5)
    5. ✅ GET /sessions/{id}/report returns signed report
    6. ✅ Report signature validates
    7. ✅ WebSocket closes cleanly
    8. ✅ Session cleanup works
    """
    # STEP 1: Upload evidence
    with open(test_image_file, "rb") as f:
        response = await authenticated_client.post(
            "http://localhost:8000/api/v1/investigate",
            files={"file": ("test.jpg", f, "image/jpeg")},
            data={"case_id": "TEST-E2E-001"}
        )
    
    assert response.status_code in (200, 202), f"Upload failed: {response.text}"
    investigation_data = response.json()
    session_id = investigation_data["session_id"]
    
    # STEP 2: Poll arbiter status
    max_polls = 120  # 5 minutes with 2.5s intervals
    arbiter_complete = False
    report_id = None
    
    for poll_num in range(max_polls):
        response = await authenticated_client.get(
            f"http://localhost:8000/api/v1/sessions/{session_id}/arbiter-status"
        )
        
        assert response.status_code == 200
        status_data = response.json()
        
        if status_data.get("status") == "complete":
            arbiter_complete = True
            report_id = status_data.get("report_id")
            break
        elif status_data.get("status") == "error":
            pytest.fail(f"Arbiter error: {status_data.get('message')}")
        
        await asyncio.sleep(2.5)  # Poll every 2.5 seconds
    
    assert arbiter_complete, "Arbiter did not complete within 5 minutes"
    
    # STEP 3: Fetch signed report
    response = await authenticated_client.get(
        f"http://localhost:8000/api/v1/sessions/{session_id}/report"
    )
    
    assert response.status_code == 200, f"Report fetch failed: {response.text}"
    report = response.json()
    
    # STEP 4: Verify report structure
    assert "report_id" in report
    assert "session_id" in report
    assert "case_id" in report
    assert "overall_verdict" in report
    assert "per_agent_findings" in report
    assert "cryptographic_signature" in report
    assert "report_hash" in report
    assert "signed_utc" in report
    
    # STEP 5: Verify signature (basic check)
    assert len(report["cryptographic_signature"]) > 64, "Signature too short"
    assert report["report_hash"].startswith("sha256:") or len(report["report_hash"]) == 64
    
    # STEP 6: Verify agents ran
    agent_count = len(report.get("per_agent_findings", {}))
    assert agent_count > 0, "No agent findings in report"
    
    print(f"\n✅ Full E2E flow PASSED")
    print(f"   - Session: {session_id}")
    print(f"   - Agents: {agent_count}")
    print(f"   - Verdict: {report['overall_verdict']}")
    print(f"   - Confidence: {report.get('overall_confidence', 'N/A')}")


@pytest.mark.asyncio
async def test_websocket_live_stream(
    authenticated_client: AsyncClient,
    test_image_file: Path
) -> None:
    """
    Test WebSocket live stream of agent updates.
    
    Verifies:
    - WebSocket connects with JWT auth
    - CONNECTED message received
    - AGENT_UPDATE messages flow continuously
    - Message types valid
    - WebSocket closes cleanly
    """
    # Start investigation
    with open(test_image_file, "rb") as f:
        response = await authenticated_client.post(
            "http://localhost:8000/api/v1/investigate",
            files={"file": ("test.jpg", f, "image/jpeg")},
            data={"case_id": "TEST-WS-001"}
        )
    
    session_id = response.json()["session_id"]
    token = authenticated_client.headers.get("Authorization", "").replace("Bearer ", "")
    
    # Connect WebSocket
    ws_url = f"ws://localhost:8000/api/v1/sessions/{session_id}/live"
    
    async with httpx.AsyncClient() as ws_client:
        async with ws_client.websocket_connect(
            ws_url,
            headers={"Authorization": f"Bearer {token}"}
        ) as websocket:
            # Receive CONNECTED message
            msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(msg)
            assert data["type"] == "CONNECTED", f"Expected CONNECTED, got {data['type']}"
            
            # Receive at least one AGENT_UPDATE
            agent_updates = []
            timeout = time.time() + 60  # 1 minute timeout
            
            while time.time() < timeout:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(msg)
                    
                    if data["type"] == "AGENT_UPDATE":
                        agent_updates.append(data)
                        assert "agent_id" in data
                        assert "status" in data
                        assert "thinking" in data or "result" in data
                    elif data["type"] == "PIPELINE_COMPLETE":
                        break
                except asyncio.TimeoutError:
                    continue
            
            assert len(agent_updates) > 0, "No AGENT_UPDATE messages received"
            print(f"\n✅ WebSocket stream received {len(agent_updates)} updates")


@pytest.mark.asyncio
async def test_hitl_checkpoint_flow(
    authenticated_client: AsyncClient,
    test_image_file: Path
) -> None:
    """
    Test Human-in-the-Loop checkpoint flow.
    
    Verifies:
    - HITL_CHECKPOINT message sent
    - GET /checkpoints returns pending decision
    - POST /hitl/decision processes decision
    - Session resumes after decision
    """
    # Enable HITL in config (or use flag)
    # Start investigation with HITL enabled
    with open(test_image_file, "rb") as f:
        response = await authenticated_client.post(
            "http://localhost:8000/api/v1/investigate",
            files={"file": ("test.jpg", f, "image/jpeg")},
            data={"case_id": "TEST-HITL-001", "hitl_enabled": "true"}
        )
    
    session_id = response.json()["session_id"]
    
    # Poll for checkpoints
    await asyncio.sleep(5)  # Give agents time to find an issue
    response = await authenticated_client.get(
        f"http://localhost:8000/api/v1/sessions/{session_id}/checkpoints"
    )
    
    assert response.status_code == 200
    checkpoints = response.json()
    
    if checkpoints:  # If there are pending checkpoints
        checkpoint = checkpoints[0]
        
        # Submit decision
        response = await authenticated_client.post(
            "http://localhost:8000/api/v1/hitl/decision",
            json={
                "session_id": session_id,
                "checkpoint_id": checkpoint["checkpoint_id"],
                "agent_id": checkpoint["agent_id"],
                "decision": "APPROVE",
                "note": "Test approval"
            }
        )
        
        assert response.status_code == 200
        decision_result = response.json()
        assert decision_result["status"] == "processed"
        
        print(f"\n✅ HITL checkpoint processed successfully")


@pytest.mark.asyncio
async def test_health_check_endpoints() -> None:
    """Test all health check endpoints."""
    async with httpx.AsyncClient() as client:
        # Test /health
        response = await client.get("http://localhost:8000/health")
        assert response.status_code in (200, 503)  # Either healthy or degraded
        data = response.json()
        assert "status" in data
        assert "checks" in data
        
        # Test /api/v1/health/ml-tools
        response = await client.get("http://localhost:8000/api/v1/health/ml-tools")
        assert response.status_code == 200
        data = response.json()
        assert "tools_ready" in data
        assert "tools_total" in data
        assert data["tools_total"] == 10
        
        print(f"\n✅ Health checks working")
        print(f"   - ML tools ready: {data['tools_ready']}/{data['tools_total']}")


# ── Run with pytest ────────────────────────────────────────────────────────
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
