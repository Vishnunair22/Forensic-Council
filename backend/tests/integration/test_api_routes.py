"""
Integration tests for API routes
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create a test client."""
    from api.main import app
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns healthy status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "environment" in data


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root(self, client):
        """Test root returns API info."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["version"] == "1.0.3"


class TestInvestigationEndpoint:
    """Test investigation endpoints."""

    @patch("api.routes.investigation.ForensicCouncilPipeline")
    def test_investigate_requires_auth(self, mock_pipeline, client):
        """Test that investigation requires authentication."""
        # Create test file
        import io
        file_content = b"fake image content"
        files = {"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}
        data = {"case_id": "TEST-001", "investigator_id": "user1"}
        
        response = client.post(
            "/api/v1/investigate",
            files=files,
            data=data,
        )
        
        # Should require auth
        assert response.status_code in [401, 403]

    @patch("api.routes.investigation.ForensicCouncilPipeline")
    def test_investigate_invalid_file_type(self, mock_pipeline, client):
        """Test that invalid file types are rejected."""
        import io
        file_content = b"fake content"
        files = {"file": ("test.exe", io.BytesIO(file_content), "application/exe")}
        data = {"case_id": "TEST-001", "investigator_id": "user1"}
        
        response = client.post(
            "/api/v1/investigate",
            files=files,
            data=data,
        )
        
        assert response.status_code == 415


class TestSessionEndpoint:
    """Test session endpoints."""

    def test_get_session_not_found(self, client):
        """Test getting non-existent session returns 404."""
        response = client.get("/api/v1/sessions/nonexistent-session/report")
        
        assert response.status_code in [404, 202]


class TestMetricsEndpoint:
    """Test metrics endpoints."""

    def test_metrics_endpoint(self, client):
        """Test metrics endpoint returns data."""
        response = client.get("/api/v1/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
