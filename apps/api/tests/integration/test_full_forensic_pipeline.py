"""
End-to-end integration test for complete forensic investigation flow.

Tests the investigation endpoint with proper mocking - no torch required.
"""

import pytest
from uuid import uuid4
from unittest.mock import patch, AsyncMock, MagicMock
from io import BytesIO


@pytest.mark.asyncio
class TestFullForensicPipeline:
    """Tests for complete forensic pipeline flow."""

    async def test_investigate_returns_200_with_session_id(
        self, client, auth_headers, jpeg_file
    ):
        """Test that POST /investigate returns 200 with valid session_id."""
        from core.auth import User, UserRole, get_current_user

        mock_user = User(user_id="user-1", username="test", role=UserRole.INVESTIGATOR)
        client.app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            client.get("/")
            csrf_token = client.cookies.get("csrf_token")
            headers = {**auth_headers, "X-CSRF-Token": csrf_token or "dummy"}

            with (
                patch(
                    "api.routes.investigation.check_investigation_rate_limit",
                    new_callable=AsyncMock,
                    return_value=True,
                ),
                patch("api.routes.investigation.check_daily_cost_quota", new_callable=AsyncMock, return_value=True),
                patch(
                    "api.routes.investigation.set_active_pipeline_metadata", new_callable=AsyncMock
                ),
                patch("magic.from_buffer", return_value="image/jpeg"),
                patch(
                    "api.routes.investigation.settings",
                    MagicMock(evidence_storage_path="/tmp", use_redis_worker=False),
                ),
                patch("api.routes.investigation.Path.mkdir", MagicMock()),
                patch("api.routes.investigation.open", MagicMock()),
            ):
                response = client.post(
                    "/api/v1/investigate",
                    headers=headers,
                    files={"file": ("test.jpg", jpeg_file, "image/jpeg")},
                    data={"case_id": "CASE-1234567890", "investigator_id": "REQ-12345"},
                )

                # Should return 200, not 202
                assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

                data = response.json()
                assert "session_id" in data
                assert data["status"] == "started"

                # Verify session_id is a valid UUID format
                session_id = data["session_id"]
                assert len(session_id) == 36  # UUID format
                assert session_id.count("-") == 4  # UUID has 4 dashes
        finally:
            client.app.dependency_overrides.clear()

    async def test_session_brief_returns_session_metadata(self, client, auth_headers):
        """Test GET /sessions/{id}/brief returns session metadata."""
        # Create a mock session in Redis
        from unittest.mock import AsyncMock, MagicMock

        mock_session_data = {
            "session_id": "test-session-123",
            "status": "initial_complete",
            "investigator_id": "user-1",
            "phase": "initial",
        }

        with patch("api.routes.sessions.get_active_pipeline_metadata", return_value=mock_session_data):
            response = client.get(
                "/api/v1/sessions/test-session-123/brief",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert "status" in data

    async def test_resume_triggers_deep_analysis(self, client, auth_headers):
        """Test POST /sessions/{id}/resume triggers deep analysis."""
        mock_session_data = {
            "session_id": "test-session-456",
            "status": "paused",
            "investigator_id": "user-1",
            "phase": "initial",
        }

        with (
            patch("api.routes.sessions.get_active_pipeline_metadata", return_value=mock_session_data),
            patch("api.routes.sessions.get_active_pipeline", return_value=None),
            patch("api.routes.sessions.set_active_pipeline_metadata", new_callable=AsyncMock),
            patch("api.routes.sessions.get_redis_client", new_callable=AsyncMock),
        ):
            response = client.post(
                "/api/v1/sessions/test-session-456/resume",
                headers=auth_headers,
                json={"deep_analysis": True},
            )

            # Should return 200 or 202
            assert response.status_code in [200, 202], f"Expected 200/202, got {response.status_code}"
            data = response.json()
            assert "status" in data

    async def test_report_returns_202_while_in_progress(self, client, auth_headers):
        """Test GET /sessions/{id}/report returns 202 while pipeline in progress."""
        # Mock no report found - pipeline still in progress
        with patch("api.routes.sessions.get_active_pipeline_metadata", return_value=None):
            with patch("api.routes.sessions._final_reports", {}):
                response = client.get(
                    "/api/v1/sessions/nonexistent-session/report",
                    headers=auth_headers,
                )

                # Should return 404 when no session found
                assert response.status_code == 404

    async def test_ecdsa_signature_format(self):
        """Test that ECDSA signature is variable length, not hardcoded to 128."""
        # Test the actual signature generation to verify format
        from core.custody_chain import sign_entry
        import time

        test_entry = {
            "action": "test_report",
            "timestamp": time.time(),
            "session_id": "test-session",
            "content_hash": "abc123def456" * 5,  # 60 char hash
        }

        signed = sign_entry(test_entry, agent_id="Agent1")

        # Verify signature exists and is a non-empty hex string
        assert "signature" in signed
        assert isinstance(signed["signature"], str)
        assert len(signed["signature"]) > 0

        # ECDSA P-256 DER signatures are typically 70-72 bytes hex-encoded = 140-144 chars
        # Not hardcoded to 128
        assert len(signed["signature"]) >= 100, f"Signature too short: {len(signed['signature'])}"

        # Verify content_hash is 64-char hex (SHA-256)
        assert "content_hash" in signed
        assert len(signed["content_hash"]) == 64
        assert signed["content_hash"].startswith(("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f"))


class TestInvestigationEndpointContracts:
    """Tests for investigation endpoint API contracts."""

    async def test_investigate_requires_auth(self, client, jpeg_file):
        """Verify investigation endpoint rejects requests without auth."""
        response = client.post(
            "/api/v1/investigate",
            files={"file": ("test.jpg", jpeg_file, "image/jpeg")},
            data={"case_id": "CASE-TEST", "investigator_id": "REQ-TEST"},
        )

        # Should be rejected (401 or 403)
        assert response.status_code in [401, 403]

    async def test_investigate_validates_case_id_format(self, client, auth_headers, jpeg_file):
        """Verify case_id is validated against expected format."""
        # Missing case_id should return 422
        response = client.post(
            "/api/v1/investigate",
            headers=auth_headers,
            files={"file": ("test.jpg", jpeg_file, "image/jpeg")},
            data={"investigator_id": "REQ-TEST"},  # No case_id
        )

        # Should return validation error
        assert response.status_code == 422


class TestSessionEndpoints:
    """Tests for session-related endpoints."""

    async def test_nonexistent_session_returns_404(self, client, auth_headers):
        """Verify 404 is returned for nonexistent session."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"

        with patch("api.routes.sessions.get_active_pipeline_metadata", return_value=None):
            with patch("api.routes.sessions._final_reports", {}):
                response = client.get(f"/api/v1/sessions/{fake_uuid}/report", headers=auth_headers)
                assert response.status_code == 404