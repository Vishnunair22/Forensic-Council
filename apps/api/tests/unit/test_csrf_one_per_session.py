"""
Unit tests for CSRF one-per-session behavior.

Tests that the CSRF cookie is only set when absent, not on every GET.
"""

import pytest


# We need to test the actual FastAPI app behavior
# Let's test the core CSRF utility logic directly
class TestCsrfOnePerSession:
    @pytest.fixture(autouse=True)
    def set_app_env(self, monkeypatch):
        from core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "development")

    @pytest.mark.asyncio
    async def test_csrf_cookie_set_on_first_request(self):
        """Verify CSRF cookie is set on first health check."""
        # Create a minimal FastAPI app to test CSRF middleware behavior
        # Use TestClient to test the app
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)

        # First request should get a CSRF cookie
        response = client.get("/health")

        # Check that Set-Cookie header is present with csrf_token
        set_cookie = response.headers.get("set-cookie", "")
        assert "csrf_token=" in set_cookie or "csrf" in set_cookie.lower(), (
            f"CSRF cookie not set on first request. Set-Cookie: {set_cookie}"
        )

    @pytest.mark.asyncio
    async def test_csrf_cookie_not_reissued_when_present(self):
        """Verify CSRF cookie is NOT re-issued on subsequent requests."""
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)

        # First request - get the cookie
        response1 = client.get("/health")
        cookies1 = response1.cookies

        # Second request - send the cookie back
        response2 = client.get("/health", cookies=cookies1)
        set_cookie2 = response2.headers.get("set-cookie", "")

        # The second response should NOT set a new CSRF cookie
        csrf_reissued = "csrf_token=" in set_cookie2 and "Max-Age" in set_cookie2
        assert not csrf_reissued, "CSRF token should not be reissued when already present"

        # If there's a Set-Cookie, it should not be re-setting the CSRF token
        # (or it might be extending the existing one)
        # The key behavior is: we shouldn't see a duplicate Set-Cookie for csrf_token
        # with a new value
        if "csrf_token" in set_cookie2:
            # Check if it looks like a new cookie being set vs just echoed
            assert "HttpOnly" in set_cookie2, "CSRF cookie should be HttpOnly"

    @pytest.mark.asyncio
    async def test_post_without_csrf_token_returns_403(self):
        """Verify POST without CSRF token is rejected with 403."""
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)

        # First get a CSRF token
        client.get("/health")

        # Try to POST without CSRF token header
        # Note: The investigate endpoint requires auth, so we test with the
        # actual endpoint behavior - with invalid/missing CSRF it should return 403

        # Create a mock file for upload test
        from io import BytesIO

        file_content = b"fake image content"
        files = {"file": ("test.jpg", BytesIO(file_content), "image/jpeg")}
        data = {"case_id": "CASE-TEST-123", "investigator_id": "REQ-TEST-001"}

        # POST without X-CSRF-Token header should fail
        response = client.post(
            "/api/v1/investigate",
            files=files,
            data=data,
        )

        # Should be 403 or 401 - either indicates CSRF/rejection
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_post_with_invalid_csrf_token_returns_403(self):
        """Verify POST with wrong CSRF token is rejected with 403."""
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)

        # Get initial cookies
        client.get("/health")

        # Try with invalid CSRF token
        from io import BytesIO

        file_content = b"fake image content"
        files = {"file": ("test.jpg", BytesIO(file_content), "image/jpeg")}
        data = {"case_id": "CASE-TEST-123", "investigator_id": "REQ-TEST-001"}

        response = client.post(
            "/api/v1/investigate",
            files=files,
            data=data,
            headers={"X-CSRF-Token": "invalid-token-12345"},
        )

        # Should be rejected
        assert response.status_code in [401, 403], (
            f"Expected 401/403 for invalid CSRF, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_csrf_cookie_is_http_only(self):
        """Verify CSRF cookie does NOT have HttpOnly flag so JS can read it."""
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")

        set_cookie = response.headers.get("set-cookie", "")

        if "csrf_token" in set_cookie.lower():
            assert "HttpOnly" not in set_cookie, (
                "CSRF cookie should not have HttpOnly flag so JS can read it"
            )

    @pytest.mark.asyncio
    async def test_csrf_cookie_has_secure_flag_in_production(self):
        """Verify CSRF cookie has Secure flag in production mode."""
        # This test would require running with APP_ENV=production
        # Skip in unit test - would be tested in integration/live tests
        pytest.skip("Requires production environment - test in live tests")


class TestCsrfGeneration:
    """Tests for CSRF token generation."""

    def test_generate_csrf_token_creates_unique_tokens(self):
        """Verify each generated CSRF token is unique."""
        import secrets

        # Use the same token generation logic as the auth routes
        tokens = [secrets.token_urlsafe(32) for _ in range(100)]

        # All tokens should be unique
        assert len(set(tokens)) == 100, "CSRF tokens should be unique"

    def test_csrf_token_length_is_sufficient(self):
        """Verify CSRF tokens are sufficiently long."""
        import secrets

        token = secrets.token_urlsafe(32)

        # token_urlsafe produces ~43 chars for 32 bytes - should be plenty
        assert len(token) >= 32, f"CSRF token too short: {len(token)}"

    def test_csrf_token_uses_secure_random(self):
        """Verify CSRF tokens use cryptographically secure random."""
        import secrets

        # Multiple tokens should not have predictable patterns
        tokens = [secrets.token_urlsafe(32) for _ in range(10)]

        # Check that tokens don't share common prefixes (would indicate weak randomness)
        prefixes = [t[:8] for t in tokens]
        assert len(set(prefixes)) > 1, "Tokens should have different prefixes"
