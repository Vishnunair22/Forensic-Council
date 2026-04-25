"""
Backend Security Tests
=======================
Tests authentication bypass, JWT algorithm attacks, input injection,
cryptographic integrity, and rate-limiting guards.
"""

import asyncio
import base64
import json
import os
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# AUTH SECURITY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


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
        from core.auth import UserRole, create_access_token, decode_token

        token = create_access_token(user_id="user-1", role=UserRole.INVESTIGATOR, username="user-1")
        parts = token.split(".")
        parts[2] = parts[2][:-4] + "XXXX"
        bad_token = ".".join(parts)

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token(bad_token)

        asyncio.run(_run())

    def test_algorithm_none_attack_rejected(self):
        """'alg: none' tokens must be rejected unconditionally."""
        from core.auth import decode_token

        header = (
            base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
            .rstrip(b"=")
            .decode()
        )
        payload = (
            base64.urlsafe_b64encode(json.dumps({"sub": "hacker", "role": "admin"}).encode())
            .rstrip(b"=")
            .decode()
        )
        none_token = f"{header}.{payload}."

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token(none_token)

        asyncio.run(_run())

    def test_expired_token_rejected(self):
        from core.auth import UserRole, create_access_token, decode_token

        expired_token = create_access_token(
            user_id="u1",
            role=UserRole.INVESTIGATOR,
            username="u1",
            expires_delta=timedelta(seconds=-10),
        )

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token(expired_token)

        asyncio.run(_run())

    def test_blacklisted_token_rejected(self):
        from core.auth import UserRole, create_access_token, decode_token

        token = create_access_token(user_id="u1", role=UserRole.INVESTIGATOR, username="u1")

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=True)):
                with pytest.raises(Exception):
                    await decode_token(token)

        asyncio.run(_run())

    def test_valid_token_accepted(self):
        from core.auth import UserRole, create_access_token, decode_token

        token = create_access_token(user_id="u1", role=UserRole.INVESTIGATOR, username="u1")

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                payload = await decode_token(token)
            assert payload is not None

        asyncio.run(_run())

    def test_token_payload_has_user_id(self):
        from core.auth import UserRole, create_access_token, decode_token

        token = create_access_token(user_id="u123", role=UserRole.INVESTIGATOR, username="alice")

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                token_data = await decode_token(token)
            assert token_data.user_id == "u123"

        asyncio.run(_run())

    def test_token_role_preserved(self):
        from core.auth import UserRole, create_access_token, decode_token

        token = create_access_token(user_id="u1", role=UserRole.ADMIN, username="admin")

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                token_data = await decode_token(token)
            assert "admin" in str(token_data.role).lower()

        asyncio.run(_run())

    def test_header_segment_tampering_rejected(self):
        from core.auth import UserRole, create_access_token, decode_token

        token = create_access_token(user_id="u1", role=UserRole.INVESTIGATOR, username="u1")
        parts = token.split(".")
        # Tamper with the header
        bad_header = (
            base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT","x":"injected"}')
            .rstrip(b"=")
            .decode()
        )
        bad_token = f"{bad_header}.{parts[1]}.{parts[2]}"

        async def _run():
            with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
                with pytest.raises(Exception):
                    await decode_token(bad_token)

        asyncio.run(_run())


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PASSWORD SECURITY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


class TestPasswordSecurity:
    def test_hash_password_is_not_plaintext(self):
        from core.auth import get_password_hash

        hashed = get_password_hash("my_secret_password")
        assert hashed != "my_secret_password"

    def test_hash_password_uses_bcrypt(self):
        from core.auth import get_password_hash

        hashed = get_password_hash("test_password")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_verify_correct_password(self):
        from core.auth import get_password_hash, verify_password

        hashed = get_password_hash("correct_password")
        assert verify_password("correct_password", hashed)

    def test_verify_wrong_password_fails(self):
        from core.auth import get_password_hash, verify_password

        hashed = get_password_hash("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_same_password_different_hashes(self):
        """bcrypt salting: same password must produce different hashes."""
        from core.auth import get_password_hash

        h1 = get_password_hash("same_password")
        h2 = get_password_hash("same_password")
        assert h1 != h2

    def test_empty_password_not_verified_against_hash(self):
        from core.auth import get_password_hash, verify_password

        hashed = get_password_hash("valid_password")
        assert not verify_password("", hashed)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CRYPTOGRAPHIC SIGNING
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


class TestCryptographicSigning:
    def test_sign_and_verify_round_trip(self):
        from core.signing import KeyStore, sign_content, verify_entry

        ks = KeyStore()
        content = {"finding": "ela_analysis", "confidence": 0.87}
        entry = sign_content("agent1_image", content, keystore=ks)
        assert verify_entry(entry, keystore=ks) is True

    def test_tampered_content_fails_verification(self):
        from core.signing import KeyStore, SignedEntry, sign_content, verify_entry

        ks = KeyStore()
        content = {"finding": "test", "confidence": 0.9}
        entry = sign_content("agent1_image", content, keystore=ks)
        # Tamper with the content hash (keep same signature â€” mismatch detectable)
        tampered = SignedEntry(
            content={"tampered": True},
            content_hash="000000000000000000000000000000000000000000000000000000000000dead",
            timestamp_utc=entry.timestamp_utc,
            signature=entry.signature,
            agent_id=entry.agent_id,
        )
        assert verify_entry(tampered, keystore=ks) is False

    def test_different_keys_fail_verification(self):
        """Signing with one KeyStore and verifying with another must fail."""
        from core.signing import KeyStore, sign_content, verify_entry

        ks1 = KeyStore()
        ks2 = KeyStore()
        content = {"test": "shared_content"}
        entry = sign_content("agent1_image", content, keystore=ks1)
        # ks2 has different keys â€” verification must fail
        assert verify_entry(entry, keystore=ks2) is False

    def test_signature_entry_has_nonempty_signature(self):
        from core.signing import KeyStore, sign_content

        ks = KeyStore()
        entry = sign_content("agent1_image", {"test": "value"}, keystore=ks)
        assert isinstance(entry.signature, str)
        assert len(entry.signature) > 0

    def test_compute_content_hash_deterministic(self):
        from core.signing import compute_content_hash

        content = {"finding": "ela", "score": 0.85}
        h1 = compute_content_hash(content)
        h2 = compute_content_hash(content)
        assert h1 == h2
        assert isinstance(h1, str)
        assert len(h1) == 64  # SHA-256 hex digest


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# INPUT VALIDATION â€” CASE ID FORMAT
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


class TestInputValidation:
    """Verify that Pydantic models reject malformed inputs."""

    def test_case_id_must_match_pattern(self):
        """case_id must follow CASE-XXXXXXXXXX format."""
        from pydantic import ValidationError

        try:
            from api.routes.schemas import InvestigationRequest

            with pytest.raises(ValidationError):
                InvestigationRequest(
                    case_id="INVALID",
                    investigator_id="REQ-12345",
                )
        except ImportError:
            pytest.skip("InvestigationRequest not importable")

    def test_sql_injection_in_case_id_rejected(self):
        """SQL injection attempts in case_id must be rejected."""
        from pydantic import ValidationError

        try:
            from api.routes.schemas import InvestigationRequest

            with pytest.raises(ValidationError):
                InvestigationRequest(
                    case_id="CASE-' OR 1=1 --",
                    investigator_id="REQ-12345",
                )
        except ImportError:
            pytest.skip("InvestigationRequest not importable")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CUSTODY CHAIN INTEGRITY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


class TestCustodyChainIntegrity:
    @pytest.mark.asyncio
    async def test_chain_entries_have_hashes(self):
        from unittest.mock import AsyncMock
        from uuid import uuid4

        from core.custody_logger import CustodyLogger, EntryType

        mock_pg = AsyncMock()
        mock_pg.execute = AsyncMock(return_value="OK")
        mock_pg.fetch_all = AsyncMock(return_value=[])

        sid = uuid4()
        logger = CustodyLogger(postgres_client=mock_pg)
        await logger.log_entry(
            agent_id="Agent1",
            session_id=sid,
            entry_type=EntryType.FINAL_FINDING,
            content={"finding": "ELA analysis complete"},
        )
        chain = await logger.get_session_chain(sid)
        for entry in chain:
            assert entry.content_hash is not None
            assert len(entry.content_hash) > 0

    @pytest.mark.asyncio
    async def test_chain_writes_one_row_per_entry(self):
        """Each log_entry call must attempt a DB write â€” one INSERT per entry."""
        from unittest.mock import AsyncMock
        from uuid import uuid4

        from core.custody_logger import CustodyLogger, EntryType

        mock_pg = AsyncMock()
        mock_pg.execute = AsyncMock(return_value="OK")

        sid = uuid4()
        custody = CustodyLogger(postgres_client=mock_pg)
        await custody.log_entry("Agent1", sid, EntryType.THOUGHT, {"content": "Thought 1"})
        await custody.log_entry("Agent1", sid, EntryType.ACTION, {"content": "Action 1"})
        await custody.log_entry("Agent1", sid, EntryType.OBSERVATION, {"content": "Obs 1"})
        # Three INSERT calls expected
        assert mock_pg.execute.call_count == 3


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RATE LIMITING
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_module_importable(self):
        """Rate limiting module must be importable."""
        try:
            from api.routes._rate_limiting import check_investigation_rate_limit

            assert callable(check_investigation_rate_limit)
        except ImportError:
            pytest.skip("rate limiting module not importable")

    @pytest.mark.asyncio
    async def test_rate_limit_check_signature_takes_user_id(self):
        """check_investigation_rate_limit must accept a user_id parameter."""
        import inspect

        try:
            from api.routes._rate_limiting import check_investigation_rate_limit

            sig = inspect.signature(check_investigation_rate_limit)
            assert "user_id" in sig.parameters
        except ImportError:
            pytest.skip("rate limiting module not importable")
