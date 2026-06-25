"""
Priority-Based Quota Manager for Free-Tier API Optimization.

Ensures critical API calls (Agent 1 vision, Arbiter synthesis) get priority
over optional calls (per-agent synthesis, ReAct reasoning).
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from core.structured_logging import get_logger

logger = get_logger(__name__)

# ── Per-investigation token budget ──────────────────────────────────────────
# Free-tier math: llama-3.3-70b-versatile has ~12K TPM. One investigation must
# fits inside a single TPM window, with ~4800 tokens RESERVED for the final-report
# refiner (the single most important LLM call). Synthesis calls that would invade
# the reserve are rejected so the caller falls back to the deterministic template.
# Env-overridable (os.environ-with-default — same style as ml_subprocess.py).
INVESTIGATION_TOKEN_BUDGET = int(os.environ.get("INVESTIGATION_TOKEN_BUDGET", "30000") or "30000")
REFINER_RESERVE_TOKENS = int(os.environ.get("REFINER_RESERVE_TOKENS", "4800") or "4800")


@dataclass
class QuotaAllocation:
    """Per-provider quota allocation strategy."""
    # Critical: Must succeed for meaningful results
    critical_reserve_pct: float = 0.40  # 40% reserved for critical calls
    # High: Improves quality significantly
    high_priority_pct: float = 0.35     # 35% for high-priority
    # Medium: Nice to have
    medium_priority_pct: float = 0.20   # 20% for medium
    # Low: Optional enhancements
    low_priority_pct: float = 0.05      # 5% for low priority


class QuotaManager:
    """
    Intelligent quota distribution for free-tier API limits.

    Priority Levels:
    - CRITICAL: Agent 1 vision (initial+deep), Arbiter final synthesis
    - HIGH: Agent 3 vision (object grounding), Agent 5 vision (metadata visual)
    - MEDIUM: Per-agent text synthesis (post-analysis narratives)
    - LOW: ReAct LLM reasoning, self-reflection passes
    """

    # Priority definitions
    PRIORITY_CRITICAL = "critical"
    PRIORITY_HIGH = "high"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_LOW = "low"

    def __init__(self, provider: str, rpm_limit: int, rpd_limit: int):
        self.provider = provider
        self.rpm_limit = rpm_limit
        self.rpd_limit = rpd_limit
        self.allocation = QuotaAllocation()

        # Tracking
        self._minute_calls: dict[str, list[datetime]] = {
            "critical": [], "high": [], "medium": [], "low": []
        }
        self._daily_calls: dict[str, int] = {
            "critical": 0, "high": 0, "medium": 0, "low": 0
        }
        self._lock = asyncio.Lock()
        self._last_reset = datetime.now()

    async def can_make_call(
        self,
        priority: Literal["critical", "high", "medium", "low"],
        estimated_tokens: int = 1000
    ) -> tuple[bool, str]:
        """
        Check if call is allowed based on priority and current quota.

        Returns:
            (allowed: bool, reason: str)
        """
        async with self._lock:
            self._cleanup_old_calls()

            # Calculate available quota per priority
            rpm_available = self._get_available_rpm(priority)
            rpd_available = self._get_available_rpd(priority)

            # Check minute quota
            minute_used = len(self._minute_calls[priority])
            if minute_used >= rpm_available:
                return False, f"{self.provider} RPM limit reached for {priority} priority"

            # Check daily quota
            daily_used = self._daily_calls[priority]
            if daily_used >= rpd_available:
                return False, f"{self.provider} daily limit reached for {priority} priority"

            # Allow call
            return True, "ok"

    async def wait_for_slot(
        self,
        priority: Literal["critical", "high", "medium", "low"],
        timeout: float = 30.0,
        estimated_tokens: int = 1000,
    ) -> bool:
        """
        Block until a rate limit slot becomes available.

        Polls every 0.5s up to `timeout` seconds. Returns True once a slot
        is free, False if the timeout was reached.
        """
        deadline = datetime.now().timestamp() + timeout
        while datetime.now().timestamp() < deadline:
            allowed, reason = await self.can_make_call(priority, estimated_tokens=estimated_tokens)
            if allowed:
                return True
            await asyncio.sleep(0.5)
        logger.warning(
            f"Quota wait_for_slot timed out after {timeout}s",
            provider=self.provider,
            priority=priority,
        )
        return False

    async def record_call(
        self,
        priority: Literal["critical", "high", "medium", "low"],
        success: bool = True
    ):
        """Record API call for quota tracking."""
        async with self._lock:
            now = datetime.now()
            self._minute_calls[priority].append(now)
            self._daily_calls[priority] += 1

            logger.debug(
                "Quota recorded",
                provider=self.provider,
                priority=priority,
                success=success,
                minute_used=len(self._minute_calls[priority]),
                daily_used=self._daily_calls[priority]
            )

    def _get_available_rpm(self, priority: str) -> int:
        """Calculate available RPM for priority level."""
        allocations = {
            "critical": self.allocation.critical_reserve_pct,
            "high": self.allocation.high_priority_pct,
            "medium": self.allocation.medium_priority_pct,
            "low": self.allocation.low_priority_pct,
        }
        val = int(self.rpm_limit * allocations[priority])
        return max(1, val) if allocations[priority] > 0 and self.rpm_limit > 0 else val

    def _get_available_rpd(self, priority: str) -> int:
        """Calculate available RPD for priority level."""
        allocations = {
            "critical": self.allocation.critical_reserve_pct,
            "high": self.allocation.high_priority_pct,
            "medium": self.allocation.medium_priority_pct,
            "low": self.allocation.low_priority_pct,
        }
        val = int(self.rpd_limit * allocations[priority])
        return max(1, val) if allocations[priority] > 0 and self.rpd_limit > 0 else val

    def _cleanup_old_calls(self):
        """Remove calls older than 1 minute."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=60)

        for priority in self._minute_calls:
            self._minute_calls[priority] = [
                ts for ts in self._minute_calls[priority] if ts > cutoff
            ]

        # Reset daily at midnight
        if now.date() > self._last_reset.date():
            self._daily_calls = dict.fromkeys(self._daily_calls, 0)
            self._last_reset = now


class InvestigationTokenBudget:
    """Tracks LLM tokens consumed by a single investigation.

    The total budget covers ONE Groq TPM window (default 12K). The last
    ``refiner_reserve`` tokens (default 4800) are reserved for the final-report
    refiner: synthesis-class calls may only consume up to
    ``total_tokens - refiner_reserve``; a call that would invade the reserve is
    rejected and the caller must fall back to the deterministic template
    (tagged ``synthesis_source="deterministic_template"`` at the generation site).
    """

    def __init__(
        self,
        investigation_id: str,
        total_tokens: int | None = None,
        refiner_reserve: int | None = None,
    ):
        self.investigation_id = investigation_id
        self.total_tokens = total_tokens if total_tokens is not None else INVESTIGATION_TOKEN_BUDGET
        self.refiner_reserve = (
            refiner_reserve if refiner_reserve is not None else REFINER_RESERVE_TOKENS
        )
        self._consumed = 0
        self._lock = asyncio.Lock()

    @property
    def consumed(self) -> int:
        return self._consumed

    @property
    def remaining(self) -> int:
        return max(0, self.total_tokens - self._consumed)

    async def try_consume(self, tokens: int, job: str = "synthesis") -> tuple[bool, str]:
        """Reserve `tokens` for a call. Returns (allowed, reason).

        job="synthesis" calls may not invade the refiner reserve;
        job="refiner" may consume the full budget including the reserve.
        """
        tokens = max(0, int(tokens))
        async with self._lock:
            ceiling = (
                self.total_tokens
                if job == "refiner"
                else self.total_tokens - self.refiner_reserve
            )
            if self._consumed + tokens > ceiling:
                reason = (
                    f"investigation token budget exhausted for {job} "
                    f"({self._consumed}+{tokens}>{ceiling}; "
                    f"{self.refiner_reserve} reserved for refiner)"
                )
                logger.warning(
                    "Investigation token budget rejected call",
                    investigation_id=self.investigation_id,
                    job=job,
                    consumed=self._consumed,
                    requested=tokens,
                    ceiling=ceiling,
                )
                return False, reason
            self._consumed += tokens
            logger.debug(
                "Investigation tokens consumed",
                investigation_id=self.investigation_id,
                job=job,
                consumed=self._consumed,
                total=self.total_tokens,
            )
            return True, "ok"


# Per-investigation budgets (bounded; oldest evicted FIFO so a long-lived
# worker process cannot grow this without bound).
_investigation_budgets: dict[str, InvestigationTokenBudget] = {}
_MAX_TRACKED_INVESTIGATIONS = 256


def get_investigation_budget(investigation_id: str) -> InvestigationTokenBudget:
    """Get or create the token budget for an investigation (session id)."""
    budget = _investigation_budgets.get(investigation_id)
    if budget is None:
        if len(_investigation_budgets) >= _MAX_TRACKED_INVESTIGATIONS:
            try:
                _investigation_budgets.pop(next(iter(_investigation_budgets)))
            except StopIteration:  # pragma: no cover — racy empty dict
                pass
        budget = InvestigationTokenBudget(investigation_id)
        _investigation_budgets[investigation_id] = budget
    return budget


# Global quota managers
_quota_managers: dict[str, QuotaManager] = {}


def get_quota_manager(provider: str, rpm_limit: int, rpd_limit: int) -> QuotaManager:
    """Get or create quota manager for provider."""
    if provider not in _quota_managers:
        _quota_managers[provider] = QuotaManager(provider, rpm_limit, rpd_limit)
    return _quota_managers[provider]
