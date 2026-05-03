"""FastAPI dependency wrappers around core rate limiting."""

from __future__ import annotations

from core.config import get_settings
from core.rate_limiting import (
    COST_QUOTA_WINDOW_SECS as _COST_QUOTA_WINDOW_SECS,
)
from core.rate_limiting import (
    DAILY_COST_QUOTA_USD as _DAILY_COST_QUOTA_USD,
)
from core.rate_limiting import (
    MAX_INVESTIGATIONS_PER_USER as _MAX_INVESTIGATIONS_PER_USER,
)
from core.rate_limiting import (
    USER_RATE_WINDOW_SECS as _USER_RATE_WINDOW_SECS,
)
from core.rate_limiting import (
    check_daily_cost_quota as _core_check_daily_cost_quota,
)
from core.rate_limiting import (
    check_investigation_rate_limit as _core_check_investigation_rate_limit,
)
from core.rate_limiting import (
    mem_cost_tracker as _mem_cost_tracker,
)
from core.rate_limiting import (
    user_investigation_times as _user_investigation_times,
)


async def check_investigation_rate_limit(user_id: str) -> None:
    """Dependency wrapper for investigation start rate limits."""
    await _core_check_investigation_rate_limit(user_id, get_settings())


async def check_daily_cost_quota(user_id: str, user_role: str = "investigator") -> None:
    """Dependency wrapper for daily investigation cost quota."""
    await _core_check_daily_cost_quota(user_id, user_role, get_settings())


__all__ = [
    "_COST_QUOTA_WINDOW_SECS",
    "_DAILY_COST_QUOTA_USD",
    "_MAX_INVESTIGATIONS_PER_USER",
    "_USER_RATE_WINDOW_SECS",
    "_mem_cost_tracker",
    "_user_investigation_times",
    "check_daily_cost_quota",
    "check_investigation_rate_limit",
]
