"""
Research model gating helper.

Provides a standardized way to check if research models are enabled
and return appropriate degraded responses.
"""

from typing import Any


def check_research_model_gate() -> dict[str, Any] | None:
    """
    Check if research models are enabled.

    Returns:
        None if research models are allowed (continue to model loading)
        dict with degraded response if research models are disabled

    Usage in ml_tools:
        from tools.ml_tools._research_gate import check_research_model_gate

        def my_tool(...):
            blocked = check_research_model_gate()
            if blocked:
                return blocked  # Return the degraded response
            # ... rest of tool logic
    """
    try:
        from core.config import get_settings

        settings = get_settings()
        if not settings.enable_research_models:
            return {
                "status": "skipped",
                "degraded": True,
                "reason": "research_model_license_gate",
                "available": False,
            }
    except ImportError:
        # If config not available, allow the tool to run
        pass
    return None
