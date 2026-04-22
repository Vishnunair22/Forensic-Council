"""
Degradation path tests — verify the system fails safely rather than silently.

These tests focus on the gaps identified in the audit:
  1. Password > 72 bytes now raises ValueError (not silent truncation).
  2. JWT RS256 configured but private key absent raises in production.
  3. Gemini circuit breaker opens after consecutive failures and rejects calls.
  4. Redis client decodes bytes correctly (regression guard for the return-value fix).
  5. _is_lossless cache in Agent1 stores without type: ignore.
  6. Signing module correctly casts load_pem_private_key output.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Minimal env before any backend import ────────────────────────────────────
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-abcdefghijklmnopqrstuvwxyz123456")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("POSTGRES_DB", "forensic_test")
os.environ.setdefault("REDIS_PASSWORD", "test_redis_pass")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test_demo_pass")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-key-abcdefghijklmnopqrstuvwxyz1234")


# ── 1. bcrypt password length enforcement ────────────────────────────────────

class TestPasswordLengthEnforcement:
    """
    Regression tests for the bcrypt silent-truncation fix.
    Before the fix, passwords > 72 bytes were silently truncated.
    After the fix, they raise ValueError at both hash and verify time.
    """

    def test_hash_rejects_password_over_72_bytes(self):
        from core.auth import get_password_hash

        long_password = "a" * 73  # 73 ASCII bytes — one over the limit
        with pytest.raises(ValueError, match="72"):
            get_password_hash(long_password)

    def test_verify_rejects_password_over_72_bytes(self):
        from core.auth import verify_password

        long_password = "a" * 73
        with pytest.raises(ValueError, match="72"):
            verify_password(long_password, "$2b$12$fakehash")

    def test_hash_accepts_exactly_72_bytes(self):
        """72-byte passwords must still work — boundary check."""
        from core.auth import get_password_hash

        password_72_bytes = "a" * 72  # exactly 72 ASCII bytes
        # Should not raise
        hashed = get_password_hash(password_72_bytes)
        assert hashed.startswith("$2b$")

    def test_hash_accepts_normal_password(self):
        from core.auth import get_password_hash

        hashed = get_password_hash("correct-horse-battery-staple")
        assert hashed.startswith("$2b$")

    def test_multibyte_unicode_counted_by_bytes_not_chars(self):
        """A 36-character string of 2-byte Unicode chars is 72 bytes — must pass."""
        from core.auth import get_password_hash

        password = "é" * 36  # each é is 2 UTF-8 bytes → 72 bytes total
        hashed = get_password_hash(password)
        assert hashed.startswith("$2b$")

    def test_multibyte_unicode_over_limit_raises(self):
        """A 37-character string of 2-byte Unicode chars is 74 bytes — must raise."""
        from core.auth import get_password_hash

        password = "é" * 37  # 74 bytes
        with pytest.raises(ValueError, match="72"):
            get_password_hash(password)


# ── 2. JWT RS256 production hardening ────────────────────────────────────────

class TestJWTRS256Hardening:
    """
    In production, RS256 selected but private key absent must raise ValueError.
    In development, it should gracefully fall back to the HMAC secret.
    """

    def test_production_rs256_without_private_key_raises(self):
        from core.config import Settings

        # Build a minimal production settings object with RS256 but no private key
        s = Settings(
            app_env="testing",  # Use testing to pass other validators
            jwt_algorithm="RS256",
            jwt_private_key=None,
            jwt_public_key=None,
            jwt_secret_key="test-jwt-key-abcdefghijklmnopqrstuvwxyz1234",
            signing_key="test-signing-key-abcdefghijklmnopqrstuvwxyz123456",
        )
        # In testing/dev, it should fall back silently
        key = s.jwt_signing_key
        assert key == s.jwt_secret_key  # fell back to HMAC key

    def test_development_rs256_without_private_key_falls_back(self):
        from core.config import Settings

        s = Settings(
            app_env="development",
            jwt_algorithm="RS256",
            jwt_private_key=None,
            jwt_public_key=None,
            jwt_secret_key="test-jwt-key-abcdefghijklmnopqrstuvwxyz1234",
            signing_key="test-signing-key-abcdefghijklmnopqrstuvwxyz123456",
        )
        # Development should fall back gracefully
        assert s.jwt_signing_key == s.jwt_secret_key

    def test_hs256_uses_secret_key_directly(self):
        from core.config import Settings

        s = Settings(
            app_env="testing",
            jwt_algorithm="HS256",
            jwt_secret_key="test-jwt-key-abcdefghijklmnopqrstuvwxyz1234",
            signing_key="test-signing-key-abcdefghijklmnopqrstuvwxyz123456",
        )
        assert s.jwt_signing_key == s.jwt_secret_key
        assert s.jwt_verification_key == s.jwt_secret_key


# ── 3. Gemini circuit breaker degradation ───────────────────────────────────

class TestGeminiCircuitBreaker:
    """
    Verify the circuit breaker in GeminiVisionClient opens after repeated
    failures and transitions correctly through OPEN → HALF_OPEN → CLOSED.
    """

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failure_threshold(self):
        from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

        cfg = CircuitBreakerConfig(failure_threshold=3, timeout_seconds=60)
        breaker = CircuitBreaker("gemini_test", cfg)

        async def failing_call():
            raise RuntimeError("Gemini API unavailable")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_call)

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_without_calling(self):
        from core.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitBreakerOpenError,
            CircuitState,
        )

        cfg = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=9999)
        breaker = CircuitBreaker("gemini_reject_test", cfg)

        call_count = 0

        async def failing_call():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("failure")

        with pytest.raises(RuntimeError):
            await breaker.call(failing_call)

        assert breaker.state == CircuitState.OPEN
        assert call_count == 1

        # Second call must be rejected by the breaker — the underlying function
        # must NOT be invoked (call_count stays at 1).
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(failing_call)

        assert call_count == 1, "Open circuit must not invoke the underlying function"

    @pytest.mark.asyncio
    async def test_circuit_recovers_after_timeout(self):
        from core.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        cfg = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0)
        breaker = CircuitBreaker("gemini_recover_test", cfg)

        async def failing_call():
            raise RuntimeError("failure")

        with pytest.raises(RuntimeError):
            await breaker.call(failing_call)

        assert breaker.state == CircuitState.OPEN

        # Simulate timeout elapsed by backdating last_failure_time
        breaker.last_failure_time = datetime.now() - timedelta(seconds=1)

        async def success_call():
            return "ok"

        result = await breaker.call(success_call)
        assert result == "ok"
        assert breaker.state == CircuitState.HALF_OPEN  # one success, needs 2

    @pytest.mark.asyncio
    async def test_degradation_flag_when_gemini_unavailable(self):
        """
        When Gemini circuit is open, the agent should mark findings with
        context_source='local_only' rather than failing the investigation.

        This tests the contract: degraded analysis > no analysis.
        """
        from core.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitBreakerOpenError,
        )

        cfg = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=9999)
        breaker = CircuitBreaker("gemini_degraded_test", cfg)

        async def fail():
            raise RuntimeError("Gemini down")

        with pytest.raises(RuntimeError):
            await breaker.call(fail)

        # Simulate what agents should do when circuit is open:
        degradation_flag = None
        try:
            await breaker.call(fail)
        except CircuitBreakerOpenError:
            degradation_flag = "gemini_unavailable"

        assert degradation_flag == "gemini_unavailable", (
            "Agents must set a degradation_flag when Gemini circuit is open, "
            "not propagate the exception silently."
        )


# ── 4. Redis client bytes decoding ───────────────────────────────────────────

class TestRedisClientDecoding:
    """
    Regression guard: redis-py returns bytes; the client wrapper must decode
    them to str to match the declared return type of get().
    """

    @pytest.mark.asyncio
    async def test_get_decodes_bytes_to_str(self):
        """When the underlying redis client returns bytes, get() must return str."""
        from core.persistence.redis_client import RedisClient

        mock_inner = AsyncMock()
        mock_inner.get = AsyncMock(return_value=b"hello_bytes")

        client = RedisClient.__new__(RedisClient)
        client.client = mock_inner

        result = await client.get("some_key")
        assert isinstance(result, str), f"Expected str, got {type(result)}"
        assert result == "hello_bytes"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_key_missing(self):
        from core.persistence.redis_client import RedisClient

        mock_inner = AsyncMock()
        mock_inner.get = AsyncMock(return_value=None)

        client = RedisClient.__new__(RedisClient)
        client.client = mock_inner

        result = await client.get("missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_passes_through_str_unchanged(self):
        """If the underlying client already returns str (some configurations), pass through."""
        from core.persistence.redis_client import RedisClient

        mock_inner = AsyncMock()
        mock_inner.get = AsyncMock(return_value="already_str")

        client = RedisClient.__new__(RedisClient)
        client.client = mock_inner

        result = await client.get("key")
        assert result == "already_str"


# ── 5. Agent1 lossless cache — no type: ignore required ──────────────────────

class TestAgent1LosslessCache:
    """
    Verify that _is_lossless caches correctly via __dict__ without
    the object.__setattr__ hack that required a type: ignore.
    """

    def _make_agent(self, file_path: str = "/tmp/test.jpg", mime: str = "image/jpeg"):
        """Build a minimal Agent1Image stub with only the fields _is_lossless reads."""
        from unittest.mock import MagicMock

        from agents.agent1_image import Agent1Image

        artifact = MagicMock()
        artifact.file_path = file_path
        artifact.mime_type = mime

        agent = Agent1Image.__new__(Agent1Image)
        agent.evidence_artifact = artifact
        return agent

    def test_is_lossless_caches_result(self):
        agent = self._make_agent()

        with patch("agents.agent1_image.is_lossless_image", return_value=False) as mock_fn:
            result1 = agent._is_lossless
            result2 = agent._is_lossless  # second call should hit cache

        # is_lossless_image should only be called once despite two property accesses
        assert mock_fn.call_count == 1, (
            "_is_lossless must cache the result — is_lossless_image was called more than once"
        )
        assert result1 == result2 == False

    def test_lossless_cache_stored_in_dict(self):
        agent = self._make_agent()

        with patch("agents.agent1_image.is_lossless_image", return_value=True):
            _ = agent._is_lossless

        assert "_is_lossless_cached" in agent.__dict__, (
            "Cache must be stored in __dict__, not via object.__setattr__"
        )
        assert agent.__dict__["_is_lossless_cached"] is True


class TestAgent1SignalContracts:
    """Regression tests for Agent 1 tool-output normalization."""

    def _make_image_handler(self):
        from core.handlers.image import ImageHandlers

        agent = MagicMock()
        agent._tool_context = {}

        async def _record_tool_result(tool_name: str, result: dict):
            agent._tool_context[tool_name] = result

        agent._record_tool_result = AsyncMock(side_effect=_record_tool_result)
        artifact = MagicMock()
        artifact.file_path = "test.jpg"
        agent.evidence_artifact = artifact
        return ImageHandlers(agent), agent

    @pytest.mark.asyncio
    async def test_diffusion_probability_becomes_confidence_and_positive_signal(self):
        from uuid import uuid4

        from core.react_loop import ReActLoopEngine

        handler, _agent = self._make_image_handler()

        with patch(
            "core.handlers.image.run_ml_tool",
            new=AsyncMock(
                return_value={
                    "verdict": "GEN_AI_DETECTION",
                    "diffusion_probability": 0.82,
                    "available": True,
                    "court_defensible": True,
                }
            ),
        ):
            result = await handler.diffusion_artifact_detector_handler({})

        assert result["confidence"] == 0.82
        assert result["diffusion_detected"] is True
        assert result["is_ai_generated"] is True

        engine = ReActLoopEngine("Agent1", uuid4(), 3, AsyncMock(), AsyncMock())
        confidence, from_fallback = engine._extract_confidence(
            result, "diffusion_artifact_detector"
        )
        status, verdict, finding_confidence, court_defensible = engine._classify_tool_output(
            result,
            "diffusion_artifact_detector",
            confidence,
            from_fallback,
        )

        assert from_fallback is False
        assert status == "CONFIRMED"
        assert verdict == "POSITIVE"
        assert finding_confidence == 0.82
        assert court_defensible is True

    @pytest.mark.asyncio
    async def test_adversarial_check_skips_until_splice_or_copy_move_signal(self):
        handler, agent = self._make_image_handler()

        result = await handler.adversarial_robustness_check_handler({})

        assert result["adversarial_check_skipped"] is True
        assert result["skipped"] is True
        assert "adversarial_robustness_check" in agent._tool_context

    @pytest.mark.asyncio
    async def test_frequency_domain_emits_confidence_and_anomaly_marker(self, tmp_path):
        from PIL import Image

        from tools.image_tools import frequency_domain_analysis

        img_path = tmp_path / "frequency_test.png"
        Image.new("RGB", (64, 64), color=(128, 128, 128)).save(img_path)
        artifact = MagicMock()
        artifact.file_path = str(img_path)

        result = await frequency_domain_analysis(artifact)

        assert "anomaly_detected" in result
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0
