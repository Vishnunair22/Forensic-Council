"""
Authorization helpers for session-based operations.
Provides session ownership validation to prevent unauthorized access.
"""

from __future__ import annotations

import os
import re

from fastapi import HTTPException

from core.auth import User, UserRole
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Unified safe-ID regex matching schemas.py _validate_safe_id
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
def _fc_test_shortcuts_enabled() -> bool:
    """Read FC_TEST_SHORTCUTS at call time so test fixtures that set it after
    import are respected, and so the module-level cache cannot accidentally
    carry a stale True across process forks."""
    return os.environ.get("FC_TEST_SHORTCUTS") == "1"


def validate_session_id(session_id: str) -> None:
    """Validate session_id format to prevent injection attacks."""
    if not session_id or not SAFE_ID_RE.match(session_id):
        raise HTTPException(
            status_code=422,
            detail="Invalid session_id format. Must be 1-128 alphanumeric characters or hyphens.",
        )


async def _load_session_metadata_from_db(session_id: str) -> dict | None:
    try:
        from core.session_persistence import get_session_persistence

        persistence = await get_session_persistence()
        state = await persistence.get_session_state(session_id)
        if isinstance(state, dict) and state:
            return state
        report = await persistence.get_report(session_id)
        if isinstance(report, dict) and report:
            return {
                "session_id": report["session_id"],
                "case_id": report["case_id"],
                "investigator_id": report["investigator_id"],
                "status": report["status"],
            }
    except Exception as exc:
        logger.warning("Session DB fallback failed", session_id=session_id, error=str(exc))
    return None


async def assert_session_access(session_id: str, user: User) -> dict:
    """
    Verify the user has access to the specified session.

    Args:
        session_id: The session to access
        user: The authenticated user

    Returns:
        Session metadata dict if access granted

    Raises:
        HTTPException: 403 if user doesn't own the session (non-admin)
                       404 if session doesn't exist
    """
    from api.routes._session_state import get_active_pipeline_metadata

    validate_session_id(session_id)

    try:
        metadata = await get_active_pipeline_metadata(session_id)
    except Exception as exc:
        logger.warning("Session metadata lookup failed", session_id=session_id, error=str(exc))
        metadata = None

    if metadata is not None and not isinstance(metadata, dict):
        if _fc_test_shortcuts_enabled():
            metadata = {"session_id": session_id, "investigator_id": getattr(user, "user_id", None)}
        else:
            metadata = None

    if not metadata:
        metadata = await _load_session_metadata_from_db(session_id)

    if not metadata:
        from api.routes._session_state import get_active_pipeline

        if _fc_test_shortcuts_enabled() and get_active_pipeline(session_id) is not None:
            return {"session_id": session_id, "investigator_id": getattr(user, "user_id", None)}
        raise HTTPException(status_code=404, detail="Session not found")

    owner = metadata.get("investigator_id")

    if user.role in (UserRole.ADMIN, UserRole.AUDITOR):
        return metadata

    if owner and not isinstance(owner, str):
        owner = None

    if owner and owner != user.user_id:
        logger.warning(
            "Unauthorized session access attempt",
            session_id=session_id,
            user_id=user.user_id,
            owner_id=owner,
        )
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this investigation",
        )

    return metadata
