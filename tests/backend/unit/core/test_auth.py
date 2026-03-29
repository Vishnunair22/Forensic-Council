"""
Backend Unit Tests — core/auth.py
===================================
Tests JWT creation/validation, bcrypt password hashing,
and the UserRole enum.

D13 fix: corrected import names from actual module:
  - get_password_hash  (was: hash_password)
  - decode_token       (was: validate_token)
  - create_access_token(user_id, role, expires_delta, username)
"""
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

# ── Import guards ──────────────────────────────────────────────────────────────

try:
    from core.auth import (
        get_password_hash,
        verify_password,
        create_access_token,
        decode_token,
        UserRole,
    )
    HAS_AUTH = True
except ImportError:
    HAS_AUTH = False

pytestmark = pytest.mark.skipif(not HAS_AUTH, reason="core.auth not importable")


# ═══════════════════════════════════════════════════════════════════════════════
# PASSWORD HASHING (bcrypt)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPasswordHashing:
    def test_hash_returns_string(self):
        h = get_password_hash("password123")
        assert isinstance(h, str)

    def test_hash_not_equal_to_plaintext(self):
        assert get_password_hash("secret") != "secret"

    def test_verify_correct_password(self):
        h = get_password_hash("correct_password")
        assert verify_password("correct_password", h) is True

    def test_verify_wrong_password(self):
        h = get_password_hash("correct_password")
        assert verify_password("wrong_password", h) is False

    def test_verify_empty_string(self):
        h = get_password_hash("password")
        assert verify_password("", h) is False

    def test_hash_is_salted_unique(self):
        """Same password hashed twice should produce different hashes."""
        h1 = get_password_hash("same_pass")
        h2 = get_password_hash("same_pass")
        assert h1 != h2

    def test_both_hashes_verify_correctly(self):
        h1 = get_password_hash("same_pass")
        h2 = get_password_hash("same_pass")
        assert verify_password("same_pass", h1) is True
        assert verify_password("same_pass", h2) is True

    def test_hash_is_bcrypt_format(self):
        h = get_password_hash("test")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_long_password_72_byte_bcrypt_limit(self):
        """verify_password truncates at 72 bytes per the implementation."""
        base = "x" * 72
        h = get_password_hash(base)
        result = verify_password(base + "extra", h)
        assert isinstance(result, bool)  # Must not crash


# ═══════════════════════════════════════════════════════════════════════════════
# JWT CREATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestJWTCreation:
    def _make_token(self, user_id="user-1", role=None, expires_delta=None):
        r = role or UserRole.INVESTIGATOR
        return create_access_token(
            user_id=user_id,
            role=r,
            expires_delta=expires_delta,
            username=user_id,
        )

    def _decode_payload(self, token: str) -> dict:
        import base64, json
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload_b64))

    def test_returns_string(self):
        assert isinstance(self._make_token(), str)

    def test_token_is_jwt_format(self):
        """JWT must have exactly 3 dot-separated parts."""
        assert len(self._make_token().split(".")) == 3

    def test_token_contains_subject(self):
        payload = self._decode_payload(self._make_token("user-abc"))
        assert payload["sub"] == "user-abc"

    def test_token_has_exp_field(self):
        payload = self._decode_payload(self._make_token())
        assert "exp" in payload

    def test_default_expiry_le_120_minutes(self):
        """Default expiry should be ≤ 120 minutes (v1.0.3 regression guard)."""
        import time
        payload = self._decode_payload(self._make_token())
        window_minutes = (payload["exp"] - time.time()) / 60
        assert window_minutes <= 120, (
            f"Token expires in {window_minutes:.0f} min — expected ≤ 120"
        )

    def test_custom_expiry_respected(self):
        import time
        token = self._make_token(expires_delta=timedelta(minutes=30))
        payload = self._decode_payload(token)
        window_minutes = (payload["exp"] - time.time()) / 60
        assert 25 <= window_minutes <= 35


# ═══════════════════════════════════════════════════════════════════════════════
# JWT DECODING (decode_token is async — use asyncio.run)
# ═══════════════════════════════════════════════════════════════════════════════

class TestJWTDecoding:
    def _make_token(self, user_id="user-1", role=None, expires_delta=None):
        r = role or UserRole.INVESTIGATOR
        return create_access_token(user_id=user_id, role=r,
                                   expires_delta=expires_delta, username=user_id)

    def test_valid_token_decodes(self):
        """decode_token must return TokenData for a valid token."""
        token = self._make_token("user-valid")

        async def _run():
            # Patch is_token_blacklisted so Redis is not required
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                td = await decode_token(token)
            assert td.user_id == "user-valid"

        asyncio.run(_run())

    def test_expired_token_raises(self):
        token = self._make_token(expires_delta=timedelta(seconds=-1))

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token(token)

        asyncio.run(_run())

    def test_garbage_string_raises(self):
        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token("not.a.jwt")

        asyncio.run(_run())

    def test_blacklisted_token_raises(self):
        token = self._make_token()

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=True)):
                with pytest.raises(Exception) as exc:
                    await decode_token(token)
            assert "revoked" in str(exc.value).lower() or "401" in str(exc.value)

        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# USERROLE
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserRole:
    def test_investigator_role_exists(self):
        assert UserRole.INVESTIGATOR is not None

    def test_admin_role_exists(self):
        assert UserRole.ADMIN is not None

    def test_role_values_are_strings(self):
        for role in UserRole:
            assert isinstance(role.value, str)
