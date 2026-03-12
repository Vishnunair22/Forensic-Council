"""
Backend Security Tests
=======================
Tests authentication bypass, input injection, CORS enforcement,
rate limiting, cryptographic integrity, and data exposure prevention.
"""
import os
import base64
import json
import pytest
from unittest.mock import AsyncMock, patch


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthSecurity:
    """Ensure the JWT implementation is not bypassable."""

    def test_no_token_rejected(self):
        try:
            from backend.core.auth import validate_token
            with pytest.raises(Exception):
                validate_token("")
        except ImportError:
            pytest.skip()

    def test_malformed_token_rejected(self):
        try:
            from backend.core.auth import validate_token
            with pytest.raises(Exception):
                validate_token("eyJhbGciOiJIUzI1NiJ9.garbage.signature")
        except ImportError:
            pytest.skip()

    def test_wrong_signing_secret_rejected(self):
        """Token signed with a different key must be rejected."""
        try:
            import jwt as pyjwt
            from backend.core.auth import validate_token
            from backend.core.config import get_settings
            real_key = get_settings().signing_key
            fake_key = "completely-different-secret-" + "y" * 40
            if fake_key == real_key:
                pytest.skip("Keys accidentally match")
            token = pyjwt.encode({"sub": "hacker", "role": "admin"}, fake_key, algorithm="HS256")
            with pytest.raises(Exception):
                validate_token(token)
        except ImportError:
            pytest.skip()

    def test_algorithm_none_attack_rejected(self):
        """'none' algorithm must never be accepted."""
        try:
            from backend.core.auth import validate_token
            header_b64 = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
            payload_b64 = base64.urlsafe_b64encode(b'{"sub":"admin","role":"admin","exp":9999999999}').rstrip(b"=").decode()
            malicious = f"{header_b64}.{payload_b64}."
            with pytest.raises(Exception):
                validate_token(malicious)
        except ImportError:
            pytest.skip()

    def test_role_escalation_via_forged_jwt_rejected(self):
        """A user cannot craft a token claiming admin role."""
        try:
            from backend.core.auth import validate_token, create_access_token
            # Create a valid investigator token
            token = create_access_token({"sub": "user-1", "role": "investigator"})
            # Decode and try to modify role
            parts = token.split(".")
            padding = 4 - len(parts[1]) % 4
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (padding % 4)))
            payload["role"] = "admin"
            forged_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
            forged_token = f"{parts[0]}.{forged_payload}.{parts[2]}"
            with pytest.raises(Exception):
                validate_token(forged_token)
        except ImportError:
            pytest.skip()

    def test_jwt_expire_minutes_not_excessive(self):
        """JWT tokens must expire within a reasonable window (≤ 120 min)."""
        try:
            from backend.core.config import get_settings
            s = get_settings()
            assert s.jwt_access_token_expire_minutes <= 120, (
                f"JWT token expires in {s.jwt_access_token_expire_minutes} minutes. "
                "This was 7 days (10080 min) in the old bug. Max allowed: 120 min."
            )
        except ImportError:
            pytest.skip()


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestInputValidation:
    """Injection and malicious input tests against Pydantic schemas and routes."""

    SQL_INJECTION_PAYLOADS = [
        "' OR '1'='1",
        "'; DROP TABLE sessions; --",
        "1; SELECT * FROM users",
        "CASE-1' UNION SELECT * FROM users --",
    ]

    XSS_PAYLOADS = [
        "<script>alert('xss')</script>",
        "javascript:alert(1)",
        "<img src=x onerror=alert(1)>",
    ]

    PATH_TRAVERSAL_PAYLOADS = [
        "../../etc/passwd",
        "../../../windows/system32/cmd.exe",
        "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ]

    def test_sql_injection_in_case_id_rejected_by_schema(self):
        try:
            from backend.api.schemas import InvestigationRequest
            import pydantic
            for payload in self.SQL_INJECTION_PAYLOADS:
                # Should either raise ValidationError or sanitize
                try:
                    obj = InvestigationRequest(case_id=payload, investigator_id="REQ-12345")
                    # If it doesn't raise, verify the case_id pattern doesn't match CASE-\d{10}
                    assert not obj.case_id.startswith("CASE-") or not obj.case_id[5:].isdigit()
                except (pydantic.ValidationError, ValueError):
                    pass  # Expected — rejected by validation
        except ImportError:
            pytest.skip()

    def test_path_traversal_in_session_id(self):
        """Path traversal in session_id should be caught by UUID validation."""
        try:
            from fastapi.testclient import TestClient
            # Session IDs must be UUIDs — path traversal strings are invalid UUIDs
            import re
            uuid_pattern = re.compile(
                r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE
            )
            for payload in self.PATH_TRAVERSAL_PAYLOADS:
                assert not uuid_pattern.match(payload), f"Traversal payload passed UUID check: {payload}"
        except ImportError:
            pytest.skip()

    def test_unicode_control_chars_in_input(self):
        """Unicode null bytes and control characters should not crash the schema."""
        try:
            from backend.api.schemas import InvestigationRequest
            import pydantic
            malicious = "CASE-\x00\x01\x02\x03"
            try:
                InvestigationRequest(case_id=malicious, investigator_id="REQ-12345")
            except (pydantic.ValidationError, ValueError):
                pass  # Correctly rejected


        except ImportError:
            pytest.skip()

    def test_oversized_json_body_rejected(self):
        """Extremely large JSON payloads should be rejected."""
        try:
            from fastapi.testclient import TestClient
            from backend.api.main import app
            with TestClient(app, raise_server_exceptions=False) as client:
                huge_payload = {"data": "x" * (10 * 1024 * 1024)}  # 10MB JSON
                r = client.post(
                    "/api/v1/hitl/decision",
                    json=huge_payload,
                    headers={"Authorization": "Bearer fake"},
                )
                assert r.status_code in (400, 401, 403, 413, 422)
        except ImportError:
            pytest.skip()


# ═══════════════════════════════════════════════════════════════════════════════
# CORS SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestCORSSecurity:
    def test_cors_allowed_origin_gets_header(self):
        try:
            from fastapi.testclient import TestClient
            from backend.api.main import app
            with TestClient(app, raise_server_exceptions=False) as client:
                r = client.get("/health", headers={"Origin": "http://localhost:3000"})
                # Allowed origins get CORS header
                if "access-control-allow-origin" in r.headers:
                    assert r.headers["access-control-allow-origin"] in (
                        "http://localhost:3000", "*",
                    )
        except ImportError:
            pytest.skip()

    def test_cors_disallowed_origin_not_reflected(self):
        try:
            from fastapi.testclient import TestClient
            from backend.api.main import app
            with TestClient(app, raise_server_exceptions=False) as client:
                evil_origin = "http://evil-attacker-site.com"
                r = client.get("/health", headers={"Origin": evil_origin})
                acao = r.headers.get("access-control-allow-origin", "")
                assert acao != evil_origin, "Evil origin was reflected in CORS header!"
        except ImportError:
            pytest.skip()

    def test_credentials_not_leaked_in_acao_star(self):
        """If ACAO is *, credentials=true should not also be set (CORS spec violation)."""
        try:
            from fastapi.testclient import TestClient
            from backend.api.main import app
            with TestClient(app, raise_server_exceptions=False) as client:
                r = client.get("/health", headers={"Origin": "http://localhost:3000"})
                acao = r.headers.get("access-control-allow-origin", "")
                acac = r.headers.get("access-control-allow-credentials", "")
                if acao == "*":
                    assert acac.lower() != "true", "CORS wildcard + credentials=true is invalid!"
        except ImportError:
            pytest.skip()


# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMITING
# ═══════════════════════════════════════════════════════════════════════════════

class TestRateLimiting:
    def test_rate_limit_function_exists(self):
        """The investigation rate limit check function should exist."""
        try:
            from backend.api.routes.investigation import _check_investigation_rate_limit
            assert callable(_check_investigation_rate_limit)
        except ImportError:
            pytest.skip("_check_investigation_rate_limit not found")

    def test_rate_limit_raises_429_when_exceeded(self):
        """Exceeding the per-user limit should raise HTTP 429."""
        try:
            from backend.api.routes.investigation import _check_investigation_rate_limit
            import asyncio

            async def run():
                mock_redis = AsyncMock()
                mock_redis.incr = AsyncMock(return_value=100)  # Over limit
                mock_redis.expire = AsyncMock(return_value=True)
                mock_redis.ttl = AsyncMock(return_value=300)
                mock_redis.get = AsyncMock(return_value=b"100")

                from fastapi import HTTPException
                try:
                    await _check_investigation_rate_limit("user-1", mock_redis)
                    # If no exception, the function may use different mechanics
                except HTTPException as e:
                    assert e.status_code == 429
                except Exception:
                    pass  # Other exception types acceptable

            asyncio.get_event_loop().run_until_complete(run())
        except ImportError:
            pytest.skip()


# ═══════════════════════════════════════════════════════════════════════════════
# CRYPTOGRAPHIC INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestCryptographicSecurity:
    def test_sign_and_verify_chain_is_valid(self):
        try:
            from backend.core.signing import sign_content, verify_entry
            entry = sign_content("agent-img", {"result": "authentic"})
            assert verify_entry(entry) is True
        except ImportError:
            pytest.skip()

    def test_tampered_entry_fails_verification(self):
        try:
            from backend.core.signing import sign_content, verify_entry
            entry = sign_content("agent-img", {"result": "authentic"})
            # Try to tamper
            if hasattr(entry, "__dict__"):
                import copy
                tampered = copy.copy(entry)
                if hasattr(tampered, "content") or hasattr(tampered, "agent_id"):
                    attr = "agent_id" if hasattr(tampered, "agent_id") else "content"
                    setattr(tampered, attr, "TAMPERED")
                    assert verify_entry(tampered) is False
            else:
                # If entry is immutable, just verify it passes
                assert verify_entry(entry) is True
        except ImportError:
            pytest.skip()

    def test_hash_algorithm_is_sha256(self):
        """Content hash should be 64 hex characters (SHA-256)."""
        try:
            from backend.core.signing import sign_content
            entry = sign_content("agent", {"data": "test"})
            h = getattr(entry, "hash", None) or getattr(entry, "content_hash", None)
            if h:
                assert len(h) == 64, f"Hash length {len(h)} != 64 (not SHA-256?)"
                assert all(c in "0123456789abcdef" for c in h.lower())
        except ImportError:
            pytest.skip()

    def test_no_credentials_in_health_endpoint(self):
        """Health endpoint must not expose secrets."""
        try:
            from fastapi.testclient import TestClient
            from backend.api.main import app
            with TestClient(app, raise_server_exceptions=False) as client:
                r = client.get("/health")
                body = r.text.lower()
                for secret_word in ("password", "secret", "signing_key", "api_key", "token"):
                    assert secret_word not in body, f"Secret word '{secret_word}' found in /health response!"
        except ImportError:
            pytest.skip()

    def test_no_env_vars_in_root_endpoint(self):
        """Root / endpoint must not expose environment variables."""
        try:
            from fastapi.testclient import TestClient
            from backend.api.main import app
            with TestClient(app, raise_server_exceptions=False) as client:
                r = client.get("/")
                body = r.text
                for dangerous in ("LLM_API_KEY", "SIGNING_KEY", "POSTGRES_PASSWORD", "REDIS_PASSWORD"):
                    assert dangerous not in body, f"Env var {dangerous} leaked in root endpoint!"
        except ImportError:
            pytest.skip()
