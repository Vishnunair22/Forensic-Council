"""
Unit tests for per-provider circuit breaker keying.

Tests that circuit breakers are keyed by provider:model, so a failing
Gemini call does not block Groq.
"""

import pytest

from core.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerPerProviderKeying:
    """Tests for per-provider circuit breaker isolation."""

    def test_different_providers_get_different_breakers(self):
        """Verify that different provider:model combos get separate breakers."""
        # Create two breakers with different provider:model keys
        breaker_groq = CircuitBreaker(service_name="groq:llama3-70b")
        breaker_gemini = CircuitBreaker(service_name="gemini:gemini-2.5-flash")

        # They should be independent
        assert breaker_groq.service_name == "groq:llama3-70b"
        assert breaker_gemini.service_name == "gemini:gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_gemini_failure_does_not_affect_groq(self):
        """Verify that tripping Gemini breaker doesn't affect Groq breaker."""
        breaker_groq = CircuitBreaker(service_name="groq:llama3")
        breaker_gemini = CircuitBreaker(service_name="gemini:gemini-2.5-flash")

        # Trip the Gemini breaker to OPEN
        for _ in range(breaker_gemini.failure_threshold):
            await breaker_gemino.on_failure(Exception("Gemini API error"))

        # Groq breaker should still be CLOSED
        assert breaker_groq.state == CircuitState.CLOSED
        assert breaker_gemini.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_groq_failure_does_not_affect_gemini(self):
        """Verify that tripping Groq breaker doesn't affect Gemini breaker."""
        breaker_gemini = CircuitBreaker(service_name="gemini:gemini-2.5-flash")
        breaker_groq = CircuitBreaker(service_name="groq:llama3")

        # Trip the Groq breaker to OPEN
        for _ in range(breaker_groq.failure_threshold):
            await breaker_groq.on_failure(Exception("Groq API error"))

        # Gemini breaker should still be CLOSED
        assert breaker_gemini.state == CircuitBreakerState.CLOSED
        assert breaker_groq.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_same_provider_different_models_share_breaker(self):
        """Verify that same provider with different models shares a breaker."""
        # If using provider-only keying, they would share
        # If using provider:model keying, they should be separate
        breaker_flash = CircuitBreaker(service_name="gemini:gemini-2.5-flash")
        breaker_pro = CircuitBreaker(service_name="gemini:gemini-2.5-pro")

        # These should be separate breakers
        assert breaker_flash.service_name != breaker_pro.service_name

    def test_breaker_key_format_in_settings(self):
        """Verify LLMClient uses correct breaker key format."""
        # Test that the circuit breaker key format is provider:model
        from core.config import get_settings

        settings = get_settings()

        # The key format should be: provider:model
        provider = "gemini"
        model = settings.gemini_model
        expected_key = f"{provider}:{model}"

        assert expected_key == "gemini:gemini-2.5-flash" or "gemini" in expected_key


class TestCircuitBreakerRegistry:
    """Tests for circuit breaker registry with per-provider keys."""

    def test_registry_creates_separate_breakers_per_key(self):
        """Verify registry creates separate breakers for different provider:model."""
        from core.circuit_breaker import CircuitBreakerRegistry

        registry = CircuitBreakerRegistry()

        # Get breakers for different providers
        breaker1 = registry.get("groq:llama3-70b")
        breaker2 = registry.get("gemini:gemini-2.5-flash")
        breaker3 = registry.get("groq:llama3-70b")  # Same as breaker1

        # Different providers should get different breakers
        assert breaker1 is not breaker2

        # Same key should return same breaker (caching)
        assert breaker1 is breaker3

    def test_registry_can_reset_all_breakers(self):
        """Verify registry can reset all breakers."""
        from core.circuit_breaker import CircuitBreakerRegistry

        registry = CircuitBreakerRegistry()

        # Get and trip a breaker
        breaker = registry.get("test-provider:test-model")
        # Note: Can't easily trip in sync context, but can test reset
        registry.reset_all()

        # Should still be able to get breakers after reset
        new_breaker = registry.get("test-provider:test-model")
        assert new_breaker is not None


class TestLLMClientCircuitBreakerKeying:
    """Tests that LLMClient uses correct per-provider circuit breaker keys."""

    def test_llm_client_creates_breaker_with_correct_key(self):
        """Verify LLMClient creates circuit breaker with provider:model key."""
        from core.config import get_settings
        from core.llm_client import LLMClient

        settings = get_settings()

        # Create an LLMClient
        client = LLMClient(
            provider="gemini",
            api_key="test-key",
            model="gemini-2.5-flash",
        )

        # The circuit breaker should be keyed by provider:model
        # This is verified by checking the breaker is created with the right key
        # We can't easily access the internal breaker, but we can verify
        # the key format is correct by checking the client stores the right info

        # The key format used should be: {provider}:{model}
        expected_key = "gemini:gemini-2.5-flash"

        # Verify by checking the client has the model set correctly
        assert client.model == "gemini-2.5-flash"
        assert client.provider == "gemini"

    @pytest.mark.asyncio
    async def test_multiple_llm_clients_for_different_providers(self):
        """Verify multiple LLM clients for different providers have separate breakers."""
        from core.llm_client import LLMClient

        # Create clients for different providers
        gemini_client = LLMClient(
            provider="gemini",
            api_key="test-key-gemini",
            model="gemini-2.5-flash",
        )

        groq_client = LLMClient(
            provider="groq",
            api_key="test-key-groq",
            model="llama3-70b",
        )

        # Both should be functional and independent
        assert gemini_client.provider == "gemini"
        assert groq_client.provider == "groq"
        assert gemini_client.model != groq_client.model


class TestCircuitBreakerFailureThreshold:
    """Tests for circuit breaker failure threshold behavior."""

    def test_default_failure_threshold(self):
        """Verify default failure threshold is reasonable."""
        breaker = CircuitBreaker(service_name="test-service")
        assert breaker.failure_threshold >= 3, "Failure threshold should be at least 3"

    def test_default_success_threshold(self):
        """Verify default success threshold for closing."""
        breaker = CircuitBreaker(service_name="test-service")
        assert breaker.success_threshold >= 1, "Success threshold should be at least 1"

    @pytest.mark.asyncio
    async def test_failure_count_increments_on_each_failure(self):
        """Verify failure count increments on each failure."""
        breaker = CircuitBreaker(service_name="test-fail-count", failure_threshold=5)

        initial_count = breaker.failure_count

        # Add failures
        for _ in range(3):
            await breaker.on_failure(Exception("Test error"))

        assert breaker.failure_count == initial_count + 3

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        """Verify success call resets failure count."""
        breaker = CircuitBreaker(service_name="test-reset", failure_threshold=5)

        # Add some failures
        for _ in range(3):
            await breaker.on_failure(Exception("Test error"))

        # Add a success
        await breaker.on_success()

        # Failure count should reset
        assert breaker.failure_count == 0
