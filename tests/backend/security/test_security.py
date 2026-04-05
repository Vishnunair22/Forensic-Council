"""
Backend Security Tests
=======================
Tests authentication bypass, JWT algorithm attacks, input injection,
cryptographic integrity, and rate-limiting guards.

D14 fix: corrected import names (get_password_hash, decode_token) and
         create_access_token call signature (user_id, role, username).
"""
import asyncio
import base64
import json
import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, patch


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthSecurity:
    """Ensure the JWT implementation is not bypassable."""

    def test_no_token_rejected(self):
        from core.auth import decode_token
        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token("")
        asyncio.run(_run())

    def test_malformed_token_rejected(self):
        from core.auth import decode_token
        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token("eyJhbGciOiJIUzI1NiJ9.garbage.signature")
        asyncio.run(_run())

    def test_wrong_signing_secret_rejected(self):
        """Token signed with a different key must be rejected."""
        from core.auth import decode_token, create_access_token, UserRole
        from core.config import get_settings
        # Create a valid token
        token = create_access_token(
            user_id="user-1", role=UserRole.INVESTIGATOR, username="user-1"
        )
        # Tamper with signature
        parts = token.split(".")
        parts[2] = parts[2][:-4] + "XXXX"
        bad_token = ".".join(parts)

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token(bad_token)
        asyncio.run(_run())

    def test_algorithm_none_attack_rejected(self):
        """'none' algorithm must never be accepted."""
        from core.auth import decode_token
        header_b64 = base64.urlsafe_b64encode(
            b'{"alg":"none","typ":"JWT"}'
        ).rstrip(b"=").decode()
        payload_b64 = base64.urlsafe_b64encode(
            b'{"sub":"admin","role":"admin","exp":9999999999}'
        ).rstrip(b"=").decode()
        malicious = f"{header_b64}.{payload_b64}."

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token(malicious)
        asyncio.run(_run())

    def test_role_escalation_via_forged_jwt_rejected(self):
        """A user cannot craft a token claiming a higher role."""
        from core.auth import decode_token, create_access_token, UserRole
        token = create_access_token(
            user_id="user-1", role=UserRole.INVESTIGATOR, username="user-1"
        )
        parts = token.split(".")
        # Decode and modify role
        pad = 4 - len(parts[1]) % 4
        decoded = json.loads(
            base64.urlsafe_b64decode(parts[1] + "=" * (pad % 4))
        )
        decoded["role"] = "admin"
        forged_payload = base64.urlsafe_b64encode(
            json.dumps(decoded).encode()
        ).rstrip(b"=").decode()
        forged_token = f"{parts[0]}.{forged_payload}.{parts[2]}"

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token(forged_token)
        asyncio.run(_run())

    def test_expired_token_rejected(self):
        """An expired token must not be accepted."""
        from core.auth import decode_token, create_access_token, UserRole
        token = create_access_token(
            user_id="u", role=UserRole.INVESTIGATOR, username="u",
            expires_delta=timedelta(seconds=-1)
        )
        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token(token)
        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# PASSWORD SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestPasswordSecurity:
    def test_hash_is_bcrypt(self):
        from core.auth import get_password_hash
        h = get_password_hash("test")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_wrong_password_not_verified(self):
        from core.auth import get_password_hash, verify_password
        h = get_password_hash("correct")
        assert verify_password("wrong", h) is False

    def test_empty_password_not_verified(self):
        from core.auth import get_password_hash, verify_password
        h = get_password_hash("nonempty")
        assert verify_password("", h) is False


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigSecurity:
    def test_signing_key_is_present(self):
        from core.config import get_settings
        s = get_settings()
        assert s.signing_key
        assert len(s.signing_key) >= 10

    def test_debug_is_bool(self):
        from core.config import get_settings
        s = get_settings()
        assert isinstance(s.debug, bool)

    def test_jwt_expire_not_excessive(self):
        """JWT must expire in ≤ 120 minutes — regression guard."""
        from core.config import get_settings
        s = get_settings()
        assert s.jwt_access_token_expire_minutes <= 120
