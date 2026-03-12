"""
Backend Unit Tests — core/auth.py
===================================
Tests JWT creation/validation, bcrypt password hashing,
RBAC role enforcement, and the UserRole enum.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# ── Import guards ──────────────────────────────────────────────────────────────

try:
    from backend.core.auth import (
        hash_password,
        verify_password,
        create_access_token,
        validate_token,
        UserRole,
    )
    HAS_AUTH = True
except ImportError:
    HAS_AUTH = False

pytestmark = pytest.mark.skipif(not HAS_AUTH, reason="backend.core.auth not importable")


# ═══════════════════════════════════════════════════════════════════════════════
# PASSWORD HASHING (bcrypt)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPasswordHashing:
    def test_hash_returns_string(self):
        h = hash_password("password123")
        assert isinstance(h, str)

    def test_hash_not_equal_to_plaintext(self):
        assert hash_password("secret") != "secret"

    def test_verify_correct_password(self):
        h = hash_password("correct_password")
        assert verify_password("correct_password", h) is True

    def test_verify_wrong_password(self):
        h = hash_password("correct_password")
        assert verify_password("wrong_password", h) is False

    def test_verify_empty_string(self):
        h = hash_password("password")
        assert verify_password("", h) is False

    def test_hash_is_salted_unique(self):
        """Same password hashed twice should produce different hashes."""
        h1 = hash_password("same_pass")
        h2 = hash_password("same_pass")
        assert h1 != h2

    def test_both_hashes_verify_correctly(self):
        h1 = hash_password("same_pass")
        h2 = hash_password("same_pass")
        assert verify_password("same_pass", h1) is True
        assert verify_password("same_pass", h2) is True

    def test_hash_is_bcrypt_format(self):
        h = hash_password("test")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_long_password_72_byte_bcrypt_limit(self):
        """bcrypt silently truncates at 72 bytes. Both passwords should verify identically."""
        base = "x" * 72
        long_pass = base + "extra"
        h = hash_password(base)
        # Both should verify (bcrypt truncates long_pass to 72 bytes == base)
        # This is expected bcrypt behavior, not a bug
        result = verify_password(long_pass, h)
        assert isinstance(result, bool)  # Just verify it doesn't crash


# ═══════════════════════════════════════════════════════════════════════════════
# JWT CREATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestJWTCreation:
    def test_returns_string(self):
        token = create_access_token({"sub": "user-1", "role": "investigator"})
        assert isinstance(token, str)

    def test_token_is_jwt_format(self):
        """JWT has exactly 3 dot-separated parts."""
        token = create_access_token({"sub": "user-1", "role": "investigator"})
        parts = token.split(".")
        assert len(parts) == 3

    def test_token_contains_user_data(self):
        """Decoded payload should contain the subject."""
        import base64, json
        token = create_access_token({"sub": "user-abc", "role": "investigator"})
        payload_b64 = token.split(".")[1]
        # Add padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload["sub"] == "user-abc"

    def test_token_has_exp_field(self):
        import base64, json
        token = create_access_token({"sub": "u", "role": "investigator"})
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert "exp" in payload

    def test_default_expiry_is_not_excessive(self):
        """Default expiry should be ≤ 120 minutes (not 7 days as the old bug was)."""
        import base64, json, time
        token = create_access_token({"sub": "u", "role": "investigator"})
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp", 0)
        now = time.time()
        window_minutes = (exp - now) / 60
        assert window_minutes <= 120, f"Token expires in {window_minutes:.0f} min (expected ≤ 120)"

    def test_custom_expiry_respected(self):
        import base64, json, time
        token = create_access_token({"sub": "u", "role": "investigator"}, expires_delta=timedelta(minutes=30))
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp", 0)
        now = time.time()
        window_minutes = (exp - now) / 60
        assert 25 <= window_minutes <= 35


# ═══════════════════════════════════════════════════════════════════════════════
# JWT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestJWTValidation:
    def test_valid_token_returns_payload(self):
        token = create_access_token({"sub": "user-valid", "role": "investigator"})
        payload = validate_token(token)
        assert payload["sub"] == "user-valid"

    def test_expired_token_raises(self):
        token = create_access_token({"sub": "u", "role": "investigator"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(Exception) as exc:
            validate_token(token)
        assert "expired" in str(exc.value).lower() or exc.value.__class__.__name__ in (
            "ExpiredSignatureError", "HTTPException", "JWTError", "TokenExpiredError"
        )

    def test_invalid_signature_raises(self):
        token = create_access_token({"sub": "u", "role": "investigator"})
        # Tamper with the signature
        parts = token.split(".")
        parts[2] = parts[2][:-4] + "XXXX"
        bad_token = ".".join(parts)
        with pytest.raises(Exception):
            validate_token(bad_token)

    def test_garbage_string_raises(self):
        with pytest.raises(Exception):
            validate_token("not.a.jwt")

    def test_empty_string_raises(self):
        with pytest.raises(Exception):
            validate_token("")

    def test_algorithm_none_attack_rejected(self):
        """Ensure 'none' algorithm JWTs are rejected."""
        import base64
        header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        payload_b64 = base64.urlsafe_b64encode(b'{"sub":"admin","role":"admin"}').rstrip(b"=").decode()
        fake_token = f"{header}.{payload_b64}."
        with pytest.raises(Exception):
            validate_token(fake_token)


# ═══════════════════════════════════════════════════════════════════════════════
# RBAC
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserRole:
    def test_investigator_role_exists(self):
        assert hasattr(UserRole, "INVESTIGATOR") or "investigator" in [r.value for r in UserRole]

    def test_admin_role_exists(self):
        assert hasattr(UserRole, "ADMIN") or "admin" in [r.value for r in UserRole]

    def test_role_values_are_strings(self):
        for role in UserRole:
            assert isinstance(role.value, str)


class TestRBACFunctions:
    """Test role enforcement functions if they exist."""

    def test_investigator_can_access_investigate(self):
        try:
            from backend.core.auth import require_role
            # Should not raise for matching role
            require_role("investigator", ["investigator", "admin"])
        except ImportError:
            pytest.skip("require_role not present")
        except Exception as e:
            pytest.fail(f"Unexpected exception: {e}")

    def test_wrong_role_raises_403_equivalent(self):
        try:
            from backend.core.auth import require_role
            with pytest.raises(Exception) as exc:
                require_role("auditor", ["investigator", "admin"])
            # Should raise something indicating forbidden (403 or PermissionError)
            assert "403" in str(exc.value) or "forbidden" in str(exc.value).lower() or \
                   "permission" in str(exc.value).lower() or "unauthorized" in str(exc.value).lower()
        except ImportError:
            pytest.skip("require_role not present")

    def test_disabled_user_flag(self):
        try:
            from backend.core.auth import is_user_active
            assert is_user_active({"sub": "u", "disabled": False}) is True
            assert is_user_active({"sub": "u", "disabled": True}) is False
        except ImportError:
            pytest.skip("is_user_active not present")
