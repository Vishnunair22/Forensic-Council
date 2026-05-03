"""
Rate Limiting & Cost Quota Routes
=============================

FastAPI dependency wrappers around core.rate_limiting.
"""

from fastapi import Depends

from api.routes._rate_limiting import (
    check_daily_cost_quota as _core_check_daily_cost_quota,
    check_investigation_rate_limit as _core_check_investigation_rate_limit,
)
from core.config import get_settings


async def check_investigation_rate_limit(user_id: str) -> None:
    """Dependency wrapper for investigation rate limit."""
    await _core_check_investigation_rate_limit(user_id, get_settings())


async def check_daily_cost_quota(user_id: str, user_role: str = "investigator") -> None:
    """Dependency wrapper for daily cost quota."""
    await _core_check_daily_cost_quota(user_id, user_role, get_settings())