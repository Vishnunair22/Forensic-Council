"""End-to-end integration test for complete forensic investigation flow."""

import pytest
from uuid import uuid4
from httpx import AsyncClient
from fastapi import status


@pytest.mark.asyncio
class TestFullForensicPipeline:
    async def test_complete_investigation_flow(
        self, client: AsyncClient, auth_headers: dict, sample_image_file
    ):
        """Test complete flow: upload → initial analysis → HITL → deep analysis → report."""
        session_id = str(uuid4())

        # 1. Upload evidence
        response = await client.post(
            "/api/v1/investigate",
            headers=auth_headers,
            files={"file": ("test.jpg", sample_image_file, "image/jpeg")},
            data={"case_id": "TEST-CASE-001", "session_id": session_id},
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        initial_data = response.json()
        assert initial_data["session_id"] == session_id

        # 2. Wait for initial analysis (mocked in test environment)
        import asyncio

        await asyncio.sleep(0.5)

        # 3. Check session state shows PAUSED for HITL
        response = await client.get(f"/api/v1/sessions/{session_id}", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        session_data = response.json()
        assert session_data["status"] in ["paused", "initial_complete"]

        # 4. Submit HITL decision for deep analysis
        response = await client.post(
            f"/api/v1/sessions/{session_id}/resume",
            headers=auth_headers,
            json={"deep_analysis": True, "decision": "PROCEED"},
        )
        assert response.status_code == status.HTTP_202_ACCEPTED

        # 5. Wait for deep analysis completion
        await asyncio.sleep(1.0)

        # 6. Retrieve final signed report
        response = await client.get(f"/api/v1/sessions/{session_id}/report", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        report = response.json()

        # Verify report structure
        assert "cryptographic_signature" in report
        assert "executive_summary" in report
        assert "per_agent_findings" in report
        assert len(report["per_agent_findings"]) >= 1  # At least one agent reported

        # Verify signature is valid format (hex string)
        assert isinstance(report["cryptographic_signature"], str)
        assert len(report["cryptographic_signature"]) == 128  # ECDSA P-256 signature

        # 7. Verify chain of custody was logged
        response = await client.get(f"/api/v1/sessions/{session_id}/custody", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        custody_log = response.json()
        assert len(custody_log) >= 4  # upload, initial, resume, report

        # Verify critical actions are logged
        actions = [entry["action"] for entry in custody_log]
        assert "evidence_uploaded" in actions
        assert "initial_analysis_complete" in actions
        assert "deep_analysis_started" in actions
        assert "report_generated" in actions
