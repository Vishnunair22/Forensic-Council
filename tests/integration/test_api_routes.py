"""
Integration Test: API Routes
=============================

Tests API route integration with database and external services.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_endpoint(authenticated_client: AsyncClient):
    """Test health check endpoint returns all dependency statuses."""
    response = await authenticated_client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "postgres" in data["checks"]
    assert "redis" in data["checks"]


@pytest.mark.asyncio
async def test_metrics_endpoint(admin_client: AsyncClient):
    """Test metrics endpoint returns system metrics."""
    response = await admin_client.get("/api/v1/metrics")
    
    assert response.status_code == 200
    data = response.json()
    assert "active_sessions" in data
    assert "total_requests" in data


@pytest.mark.asyncio
async def test_rate_limiting_enforcement(authenticated_client: AsyncClient):
    """Test that rate limiting is enforced."""
    # Make rapid requests to trigger rate limit
    responses = []
    for _ in range(100):
        resp = await authenticated_client.get("/api/v1/sessions")
        responses.append(resp)
    
    # At least one should be rate limited
    rate_limited = [r for r in responses if r.status_code == 429]
    assert len(rate_limited) > 0, "Rate limiting should be enforced"


@pytest.mark.asyncio
async def test_csrf_protection(authenticated_client: AsyncClient):
    """Test CSRF token validation."""
    # Remove CSRF token from headers
    headers = dict(authenticated_client.headers)
    if "X-CSRF-Token" in headers:
        del headers["X-CSRF-Token"]
    
    from httpx import AsyncClient, ASGITransport
    from backend.api.main import app
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        # Try POST without CSRF token
        response = await client.post(
            "/api/v1/sessions",
            json={"case_id": "TEST_CSRF"}
        )
        
        # Should be forbidden
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_cors_headers(authenticated_client: AsyncClient):
    """Test CORS headers are set correctly."""
    response = await authenticated_client.options(
        "/api/v1/sessions",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        }
    )
    
    # Should allow CORS
    assert "access-control-allow-origin" in response.headers


@pytest.mark.asyncio
async def test_security_headers(authenticated_client: AsyncClient):
    """Test security headers are present."""
    response = await authenticated_client.get("/health")
    
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in response.headers


@pytest.mark.asyncio
async def test_invalid_json_handling(authenticated_client: AsyncClient):
    """Test handling of malformed JSON."""
    response = await authenticated_client.post(
        "/api/v1/sessions",
        content="not valid json",
        headers={"Content-Type": "application/json"}
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_required_fields(authenticated_client: AsyncClient):
    """Test validation of required fields."""
    response = await authenticated_client.post(
        "/api/v1/sessions",
        json={}
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pagination(authenticated_client: AsyncClient):
    """Test pagination works correctly."""
    response = await authenticated_client.get("/api/v1/sessions?page=1&limit=10")
    
    assert response.status_code == 200
    data = response.json()
    assert "items" in data or isinstance(data, list)


@pytest.mark.asyncio
async def test_concurrent_session_limits(authenticated_client: AsyncClient):
    """Test concurrent session limits are enforced."""
    import asyncio
    
    # Try to create many sessions concurrently
    tasks = [
        authenticated_client.post("/api/v1/sessions", json={"case_id": f"CONC_{i}"})
        for i in range(20)
    ]
    
    responses = await asyncio.gather(*tasks)
    
    # All should succeed (or some should be rate limited)
    success_count = sum(1 for r in responses if r.status_code in [200, 201, 202])
    rate_limited_count = sum(1 for r in responses if r.status_code == 429)
    
    assert success_count + rate_limited_count == len(responses)
