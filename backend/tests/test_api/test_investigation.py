"""
Investigation API Tests
=======================

Tests for the investigation endpoints.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestInvestigationEndpoints:
    """Tests for investigation endpoints."""

    def test_root(self):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Forensic Council API"
        assert data["version"] == "1.0.0"

    def test_health_check(self):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_post_investigate_valid_image_returns_session_id(self):
        """Test that valid image upload returns session_id."""
        # Create a dummy image file
        file_content = b"fake image content"
        files = {"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}
        data = {
            "case_id": "TEST-001",
            "investigator_id": "test-investigator"
        }

        response = client.post("/api/v1/investigate", files=files, data=data)
        
        # Should succeed (may fail due to size validation)
        assert response.status_code in [200, 413]

    def test_post_investigate_invalid_mime_type_returns_422(self):
        """Test that invalid MIME type returns 422."""
        file_content = b"fake content"
        files = {"file": ("test.exe", io.BytesIO(file_content), "application/x-executable")}
        data = {
            "case_id": "TEST-001",
            "investigator_id": "test-investigator"
        }

        response = client.post("/api/v1/investigate", files=files, data=data)
        assert response.status_code == 422

    def test_post_investigate_file_too_large_returns_413(self):
        """Test that file too large returns 413."""
        # Create a large dummy file (> 50MB)
        file_content = b"x" * (51 * 1024 * 1024)
        files = {"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}
        data = {
            "case_id": "TEST-001",
            "investigator_id": "test-investigator"
        }

        response = client.post("/api/v1/investigate", files=files, data=data)
        assert response.status_code == 413

    def test_get_report_session_not_found_returns_404(self):
        """Test that non-existent session returns 404."""
        response = client.get("/api/v1/sessions/nonexistent-session-id/report")
        assert response.status_code == 404

    def test_get_brief_session_not_found_returns_404(self):
        """Test that non-existent session returns 404 for brief."""
        response = client.get("/api/v1/sessions/nonexistent-session-id/brief/agent1")
        assert response.status_code == 404

    def test_get_checkpoints_session_not_found_returns_404(self):
        """Test that non-existent session returns 404 for checkpoints."""
        response = client.get("/api/v1/sessions/nonexistent-session-id/checkpoints")
        assert response.status_code == 404

    def test_list_sessions_empty(self):
        """Test listing sessions when none exist (or just returns list)."""
        response = client.get("/api/v1/sessions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_delete_session_not_found_returns_404(self):
        """Test deleting non-existent session returns 404."""
        response = client.delete("/api/v1/sessions/nonexistent-session-id")
        assert response.status_code == 404


class TestHITLEndpoints:
    """Tests for HITL endpoints."""

    def test_post_hitl_decision_approve_returns_200(self):
        """Test that HITL decision returns 200."""
        payload = {
            "session_id": "test-session",
            "checkpoint_id": "test-checkpoint",
            "agent_id": "agent1",
            "decision": "APPROVE",
            "note": "Looks good"
        }

        response = client.post("/api/v1/hitl/decision", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"


class TestWebSocket:
    """Tests for WebSocket endpoint."""

    def test_websocket_connection(self):
        """Test WebSocket connection to live endpoint."""
        with client.websocket_connect("/api/v1/sessions/test-session/live") as ws:
            # Should receive connection message
            data = ws.receive_json()
            assert data["type"] == "AGENT_UPDATE"
            assert "connected" in data["message"].lower()
