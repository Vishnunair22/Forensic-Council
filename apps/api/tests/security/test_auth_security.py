"""Security-focused tests for authentication and authorization."""

import pytest
from fastapi import status
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAuthSecurity:
    async def test_jwt_signature_validation(self, client: AsyncClient):
        """Verify JWT tokens with invalid signatures are rejected."""
        invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.invalid_signature"
        response = await client.get(
            "/api/v1/sessions/test", headers={"Authorization": f"Bearer {invalid_token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_rate_limiting_enforcement(self, client: AsyncClient):
        """Test that rate limiting prevents brute-force attacks."""
        # Make rapid requests to trigger rate limit
        responses = []
        for _ in range(100):
            resp = await client.post(
                "/api/v1/auth/login", json={"email": "test@example.com", "password": "wrong"}
            )
            responses.append(resp.status_code)

        # Should have at least one 429 response
        assert status.HTTP_429_TOO_MANY_REQUESTS in responses

    async def test_sql_injection_prevention(self, client: AsyncClient, auth_headers: dict):
        """Verify SQL injection attempts are blocked."""
        malicious_case_id = "'; DROP TABLE evidence; --"
        response = await client.get(f"/api/v1/sessions/{malicious_case_id}", headers=auth_headers)
        # Should return 404 or 400, never 500 (which would indicate SQL error)
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]


@pytest.mark.asyncio
class TestSigningSecurity:
    async def test_report_signature_verification(self):
        """Verify forensic reports cannot be tampered with."""
        from core.signing import Signer, VerificationError

        signer = Signer("test-key-" + "x" * 32)
        report_data = {"verdict": "authentic", "evidence_hash": "abc123"}

        # Sign and verify legitimate report
        signature = signer.sign(report_data)
        assert signer.verify(report_data, signature) is True

        # Tamper with data - verification should fail
        tampered = report_data.copy()
        tampered["verdict"] = "manipulated"
        with pytest.raises(VerificationError):
            signer.verify(tampered, signature)
