"""
E2E Test: Full Investigation Flow
==================================

Tests the complete investigation workflow from file upload to report generation.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_investigation_workflow(authenticated_client: AsyncClient, sample_image_file):
    """Test complete investigation flow: upload → analyze → report."""
    # Step 1: Upload evidence file
    with open(sample_image_file, "rb") as f:
        upload_response = await authenticated_client.post(
            "/api/v1/investigate",
            files={"file": ("test.jpg", f, "image/jpeg")},
            data={"case_id": "TEST_CASE_001"}
        )
    
    assert upload_response.status_code == 202
    session_data = upload_response.json()
    session_id = session_data["session_id"]
    assert session_id is not None
    
    # Step 2: Monitor investigation progress via WebSocket
    # (WebSocket testing would go here in real implementation)
    
    # Step 3: Wait for completion and fetch report
    # In production, this would poll or wait for WebSocket signal
    import asyncio
    await asyncio.sleep(2)  # Simulate processing time
    
    report_response = await authenticated_client.get(
        f"/api/v1/sessions/{session_id}/report"
    )
    
    # Should return either 200 (complete) or 202 (still processing)
    assert report_response.status_code in [200, 202]
    
    if report_response.status_code == 200:
        report = report_response.json()
        assert "per_agent_findings" in report
        assert len(report["per_agent_findings"]) >= 1


@pytest.mark.asyncio
async def test_investigation_with_multiple_files(authenticated_client: AsyncClient, sample_image_file, sample_evidence_file):
    """Test investigation with multiple evidence files."""
    session_id = None
    
    # Upload first file
    with open(sample_image_file, "rb") as f:
        response1 = await authenticated_client.post(
            "/api/v1/investigate",
            files={"file": ("test.jpg", f, "image/jpeg")},
            data={"case_id": "TEST_CASE_MULTI"}
        )
    
    assert response1.status_code == 202
    session_id = response1.json()["session_id"]
    
    # Upload second file to same session
    with open(sample_evidence_file, "rb") as f:
        response2 = await authenticated_client.post(
            f"/api/v1/sessions/{session_id}/upload",
            files={"file": ("evidence.txt", f, "text/plain")}
        )
    
    assert response2.status_code in [200, 202]


@pytest.mark.asyncio
async def test_session_lifecycle(authenticated_client: AsyncClient):
    """Test session creation, retrieval, and deletion."""
    # Create session
    response = await authenticated_client.post(
        "/api/v1/sessions",
        json={"case_id": "TEST_LIFECYCLE"}
    )
    assert response.status_code == 201
    session_id = response.json()["session_id"]
    
    # Retrieve session
    get_response = await authenticated_client.get(
        f"/api/v1/sessions/{session_id}"
    )
    assert get_response.status_code == 200
    
    # List sessions
    list_response = await authenticated_client.get("/api/v1/sessions")
    assert list_response.status_code == 200
    assert any(s["session_id"] == session_id for s in list_response.json())
    
    # Delete session
    delete_response = await authenticated_client.delete(
        f"/api/v1/sessions/{session_id}"
    )
    assert delete_response.status_code == 200
    
    # Verify deletion
    get_after_delete = await authenticated_client.get(
        f"/api/v1/sessions/{session_id}"
    )
    assert get_after_delete.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_investigations(authenticated_client: AsyncClient, sample_image_file):
    """Test that multiple concurrent investigations work correctly."""
    import asyncio
    
    # Launch 3 investigations concurrently
    tasks = []
    for i in range(3):
        with open(sample_image_file, "rb") as f:
            task = authenticated_client.post(
                "/api/v1/investigate",
                files={"file": ("test.jpg", f, "image/jpeg")},
                data={"case_id": f"CONCURRENT_TEST_{i}"}
            )
            tasks.append(task)
    
    responses = await asyncio.gather(*tasks)
    
    # All should succeed
    for resp in responses:
        assert resp.status_code == 202
        assert "session_id" in resp.json()


@pytest.mark.asyncio
async def test_investigation_metadata(authenticated_client: AsyncClient, sample_image_file):
    """Test that investigation metadata is properly stored."""
    with open(sample_image_file, "rb") as f:
        response = await authenticated_client.post(
            "/api/v1/investigate",
            files={"file": ("test.jpg", f, "image/jpeg")},
            data={
                "case_id": "TEST_META",
                "investigator_notes": "Test investigation with metadata"
            }
        )
    
    assert response.status_code == 202
    session_id = response.json()["session_id"]
    
    # Retrieve session details
    details = await authenticated_client.get(f"/api/v1/sessions/{session_id}")
    assert details.status_code == 200
    
    data = details.json()
    assert data["case_id"] == "TEST_META"


@pytest.mark.asyncio
async def test_invalid_file_upload(authenticated_client: AsyncClient):
    """Test that invalid file uploads are rejected."""
    # Empty file
    import io
    response = await authenticated_client.post(
        "/api/v1/investigate",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        data={"case_id": "TEST_INVALID"}
    )
    
    # Should reject empty or invalid files
    assert response.status_code in [400, 415, 422]


@pytest.mark.asyncio
async def test_unauthorized_access(sample_image_file):
    """Test that unauthenticated users cannot start investigations."""
    from httpx import AsyncClient, ASGITransport
    from backend.api.main import app
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with open(sample_image_file, "rb") as f:
            response = await client.post(
                "/api/v1/investigate",
                files={"file": ("test.jpg", f, "image/jpeg")},
                data={"case_id": "TEST_UNAUTH"}
            )
        
        # Should require authentication
        assert response.status_code == 401
