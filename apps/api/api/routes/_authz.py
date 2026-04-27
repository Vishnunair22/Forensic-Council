"""
Authorization helpers for session-based operations.
Provides session ownership validation to prevent unauthorized access.
"""

from __future__ import annotations

import re

from fastapi import HTTPException

from core.auth import User, UserRole
from core.structured_logging import get_logger

logger = get_logger(__name__)

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9\-]{1,128}$")


def validate_session_id(session_id: str) -> None:
    """Validate session_id format to prevent injection attacks."""
    if not session_id or not SAFE_ID_RE.match(session_id):
        raise HTTPException(
            status_code=422,
            detail="Invalid session_id format. Must be 1-128 alphanumeric characters or hyphens.",
        )


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

    metadata = await get_active_pipeline_metadata(session_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="Session not found")

    owner = metadata.get("investigator_id")

    if user.role in (UserRole.ADMIN, UserRole.AUDITOR):
        return metadata

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