"""
Priority-Based Quota Manager for Free-Tier API Optimization.

Ensures critical API calls (Agent 1 vision, Arbiter synthesis) get priority
over optional calls (per-agent synthesis, ReAct reasoning).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from core.structured_logging import get_logger

logger = get_logger(__name__)


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
                f"Quota recorded",
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
            self._daily_calls = {k: 0 for k in self._daily_calls}
            self._last_reset = now


# Global quota managers
_quota_managers: dict[str, QuotaManager] = {}


def get_quota_manager(provider: str, rpm_limit: int, rpd_limit: int) -> QuotaManager:
    """Get or create quota manager for provider."""
    if provider not in _quota_managers:
        _quota_managers[provider] = QuotaManager(provider, rpm_limit, rpd_limit)
    return _quota_managers[provider]
