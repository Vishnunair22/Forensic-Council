"""
Provider Quota Guard
====================

Pre-call quota enforcement for LLM/Gemini providers. Guards the per-minute
and per-day rate limits for free-tier API keys by tracking calls in a
process-local sliding window. When a limit is reached, the guard returns
False so callers can degrade gracefully (skip, use local fallback, or
return early) rather than hitting 429s.

Usage:
    guard = ProviderQuotaGuard()
    guard.configure("gemini", rpm_limit=10, rpd_limit=1500)
    if await guard.check_and_record("gemini", "gemini-2.5-flash"):
        await call_gemini()
    else:
        return local_fallback()
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field

from core.structured_logging import get_logger

logger = get_logger(__name__)

# Per-process in-memory call tracking for quota enforcement.
# Resets on process restart — acceptable for per-session quota guards.
# Key: (provider, model)  Value: list of timestamps (Unix seconds)
_CALL_TIMESTAMPS: dict[str, list[float]] = defaultdict(list)
_TOKEN_TIMESTAMPS: dict[str, list[tuple[float, int]]] = defaultdict(list)

# Lazy lock — created on first use inside a running event loop.
# Module-level asyncio.Lock() is unsafe in Python 3.10+ when the module is
# imported before an event loop is running (e.g. in subprocesses or tests).
_TRACKING_LOCK: asyncio.Lock | None = None


def _get_tracking_lock() -> asyncio.Lock:
    global _TRACKING_LOCK
    if _TRACKING_LOCK is None:
        _TRACKING_LOCK = asyncio.Lock()
    return _TRACKING_LOCK

# Cleanup interval: remove stale timestamps older than 2 minutes.
_CLEANUP_INTERVAL_SECONDS = 120.0


@dataclass
class ProviderConfig:
    """Quota configuration for a single provider."""

    rpm_limit: int = 30
    rpd_limit: int = 1500
    tpm_limit: int | None = None  # tokens-per-minute (Groq-specific)
    enabled: bool = True
    _last_cleanup: float = field(default_factory=time.time)


@dataclass
class QuotaCheckResult:
    """Result of a quota check + record operation."""

    allowed: bool
    reason: str
    calls_in_window: int = 0
    limit: int = 0
    window_type: str = "rpm"  # "rpm" or "rpd"


def _provider_model_key(provider: str, model: str) -> str:
    return f"{provider}:{model}"


class ProviderQuotaGuard:
    """
    Process-wide quota guard for LLM/Gemini free-tier rate limits.

    Tracks call timestamps in a sliding window to prevent exceeding
    RPM/RPD limits. Not persistent — resets on process restart.
    Designed for free-tier enforcement; paid tiers should use
    provider-native retry with backoff.

    Usage:
        guard = ProviderQuotaGuard()
        guard.configure("gemini", rpm_limit=10, rpd_limit=1500)

        allowed, result = await guard.check_and_record("gemini", "gemini-2.5-flash")
        if not allowed:
            logger.warning(f"Quota guard blocked {provider}/{model}: {result.reason}")
            return local_fallback()
    """

    _configs: dict[str, ProviderConfig] = {}
    _initialized: bool = False

    @classmethod
    def configure(cls, provider: str, rpm_limit: int, rpd_limit: int, tpm_limit: int | None = None) -> None:
        """Set quota limits for a provider. Call once at startup."""
        existing = cls._configs.get(provider)
        if (
            existing
            and existing.rpm_limit == rpm_limit
            and existing.rpd_limit == rpd_limit
            and existing.tpm_limit == tpm_limit
            and existing.enabled
        ):
            return
        cls._configs[provider] = ProviderConfig(
            rpm_limit=rpm_limit, rpd_limit=rpd_limit, tpm_limit=tpm_limit, enabled=True
        )
        logger.info(
            "Provider quota guard configured",
            provider=provider,
            rpm_limit=rpm_limit,
            rpd_limit=rpd_limit,
        )

    @classmethod
    def disable_provider(cls, provider: str) -> None:
        """Disable quota enforcement for a provider (e.g. paid tier)."""
        if provider in cls._configs:
            cls._configs[provider].enabled = False
            logger.info("Provider quota guard disabled", provider=provider)

    @classmethod
    def get_config(cls, provider: str) -> ProviderConfig | None:
        """Return the quota config for a provider, or None if not configured."""
        return cls._configs.get(provider)

    @classmethod
    async def check_and_record(
        cls,
        provider: str,
        model: str,
        *,
        estimated_tokens: int = 0,
        tpm_limit_override: int | None = None,
        priority: str = "medium",
    ) -> tuple[bool, QuotaCheckResult]:
        """
        Check quota availability and record a call.

        Returns (allowed, result). If allowed=False, the caller should
        degrade gracefully rather than making the API call.

        Window order: RPM first (60-second sliding), then RPD (24-hour).
        RPM is the tighter constraint for most free-tier APIs.

        priority="critical" calls (e.g. the final-report narrative refiner) skip
        the *soft* TPM pre-block: TPM is the bucket most easily exhausted by the
        many synthesis calls in one investigation, and pre-emptively blocking the
        single most important call drops the report to the deterministic narrative.
        Critical calls instead attempt the request and rely on the provider's real
        429 + the higher-TPM-model fallback cascade. Tokens are still recorded, and
        the hard RPM/RPD request-count limits remain enforced for all priorities.
        """
        config = cls._configs.get(provider)
        if config is None or not config.enabled:
            return True, QuotaCheckResult(allowed=True, reason="provider not configured")

        async with _get_tracking_lock():
            key = _provider_model_key(provider, model)
            now = time.time()

            # Cleanup old timestamps periodically
            if now - config._last_cleanup > _CLEANUP_INTERVAL_SECONDS:
                cls._cleanup_stale(provider, model, now)
                config._last_cleanup = now

            timestamps = _CALL_TIMESTAMPS[key]

            # RPM check: calls in the last 60 seconds
            cutoff_60s = now - 60.0
            recent_calls = [ts for ts in timestamps if ts > cutoff_60s]
            rpm_count = len(recent_calls)
            rpm_limit = config.rpm_limit

            if rpm_count >= rpm_limit:
                result = QuotaCheckResult(
                    allowed=False,
                    reason=(
                        f"{provider} RPM limit reached ({rpm_count}/{rpm_limit}) — "
                        f"next allowed in ~60s"
                    ),
                    calls_in_window=rpm_count,
                    limit=rpm_limit,
                    window_type="rpm",
                )
                logger.warning(
                    f"Quota guard: RPM limit reached for {provider}/{model}",
                    count=rpm_count,
                    limit=rpm_limit,
                )
                return False, result

            effective_tpm_limit = tpm_limit_override or config.tpm_limit
            if effective_tpm_limit and estimated_tokens > 0 and priority != "critical":
                recent_tokens = [
                    item for item in _TOKEN_TIMESTAMPS[key] if item[0] > cutoff_60s
                ]
                token_count = sum(tokens for _, tokens in recent_tokens)
                if token_count + estimated_tokens > effective_tpm_limit:
                    result = QuotaCheckResult(
                        allowed=False,
                        reason=(
                            f"{provider} TPM limit would be exceeded "
                            f"({token_count + estimated_tokens}/{effective_tpm_limit})"
                        ),
                        calls_in_window=token_count,
                        limit=effective_tpm_limit,
                        window_type="tpm",
                    )
                    logger.warning(
                        "Quota guard: TPM limit reached",
                        provider=provider,
                        model=model,
                        tokens=token_count,
                        estimated_tokens=estimated_tokens,
                        limit=effective_tpm_limit,
                    )
                    return False, result

            # RPD check: calls in the last 24 hours
            cutoff_24h = now - 86400.0
            daily_calls = [ts for ts in timestamps if ts > cutoff_24h]
            rpd_count = len(daily_calls)
            rpd_limit = config.rpd_limit

            if rpd_count >= rpd_limit:
                result = QuotaCheckResult(
                    allowed=False,
                    reason=(
                        f"{provider} RPD limit reached ({rpd_count}/{rpd_limit}) — "
                        f"next allowed tomorrow"
                    ),
                    calls_in_window=rpd_count,
                    limit=rpd_limit,
                    window_type="rpd",
                )
                logger.warning(
                    f"Quota guard: RPD limit reached for {provider}/{model}",
                    count=rpd_count,
                    limit=rpd_limit,
                )
                return False, result

            # Record the call while still holding the lock so concurrent agents
            # cannot overshoot the quota between check and append.
            _CALL_TIMESTAMPS[key].append(now)
            if estimated_tokens > 0:
                _TOKEN_TIMESTAMPS[key].append((now, estimated_tokens))

        return True, QuotaCheckResult(
            allowed=True,
            reason="quota available",
            calls_in_window=rpm_count + 1,
            limit=rpm_limit,
            window_type="rpm",
        )

    @classmethod
    def _cleanup_stale(cls, provider: str, model: str, now: float) -> None:
        """Remove timestamps older than 24 hours from the call tracking."""
        key = _provider_model_key(provider, model)
        cutoff = now - 86400.0
        _CALL_TIMESTAMPS[key] = [ts for ts in _CALL_TIMESTAMPS[key] if ts > cutoff]
        _TOKEN_TIMESTAMPS[key] = [
            (ts, tokens) for ts, tokens in _TOKEN_TIMESTAMPS[key] if ts > cutoff
        ]
        # Also clean up entries with no recent calls to prevent unbounded dict growth
        if not _CALL_TIMESTAMPS[key]:
            _CALL_TIMESTAMPS.pop(key, None)
        if not _TOKEN_TIMESTAMPS[key]:
            _TOKEN_TIMESTAMPS.pop(key, None)

    @classmethod
    def clear_all(cls) -> None:
        """Clear all call tracking. Use in tests."""
        _CALL_TIMESTAMPS.clear()
        _TOKEN_TIMESTAMPS.clear()

    @classmethod
    def get_current_counts(cls, provider: str, model: str) -> tuple[int, int]:
        """Return (rpm_count, rpd_count) for a provider/model. For debugging."""
        key = _provider_model_key(provider, model)
        now = time.time()
        timestamps = _CALL_TIMESTAMPS.get(key, [])
        cutoff_60s = now - 60.0
        cutoff_24h = now - 86400.0
        rpm = len([ts for ts in timestamps if ts > cutoff_60s])
        rpd = len([ts for ts in timestamps if ts > cutoff_24h])
        return rpm, rpd


def configure_provider_quota_guards(settings) -> None:
    """Configure all provider quota guards from app settings.

    This is intentionally idempotent and cheap. API and worker processes are
    separate in Docker deployments, so both must configure their in-process
    guards before provider calls begin.
    """
    ProviderQuotaGuard.configure(
        "groq",
        rpm_limit=getattr(settings, "groq_rpm_limit", 15),
        rpd_limit=getattr(settings, "groq_rpd_limit", 15000),
        tpm_limit=getattr(settings, "groq_tpm_limit", None),
    )
    ProviderQuotaGuard.configure(
        "gemini",
        rpm_limit=getattr(settings, "gemini_rpm_limit", 5),   # was 10
        rpd_limit=getattr(settings, "gemini_rpd_limit", 1500),
    )
    ProviderQuotaGuard.configure(
        "groq_vision",
        rpm_limit=getattr(settings, "groq_vision_rpm_limit", 15),
        rpd_limit=getattr(settings, "groq_vision_rpd_limit", 14400),
    )
    ProviderQuotaGuard.configure(
        "cerebras",
        rpm_limit=getattr(settings, "cerebras_rpm_limit", 30),
        rpd_limit=getattr(settings, "cerebras_rpd_limit", 14400),
    )
