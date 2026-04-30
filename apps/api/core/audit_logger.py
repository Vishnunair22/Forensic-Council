"""
Audit Logging Module
====================

Provides structured audit logging for compliance and security monitoring.
All sensitive operations (auth, permissions, data changes) are logged here.

Usage:
    from core.audit_logger import log_sensitive_operation

    await log_sensitive_operation(
        user_id="user123",
        operation="password_change",
        resource_type="user",
        resource_id="user123",
        result="success"
    )
"""

from datetime import UTC, datetime
from typing import Any

from core.structured_logging import get_logger

audit_logger = get_logger("audit")


async def log_sensitive_operation(
    user_id: str,
    operation: str,
    resource_type: str,
    resource_id: str,
    old_value: Any | None = None,
    new_value: Any | None = None,
    result: str = "success",
    details: dict | None = None,
    ip_address: str | None = None,
):
    """
    Log sensitive operations for compliance and security auditing.

    Args:
        user_id: User who performed the operation
        operation: Type of operation (e.g., "password_change", "role_update")
        resource_type: Type of resource affected (e.g., "user", "session", "report")
        resource_id: ID of the resource affected
        old_value: Previous value (truncated to 100 chars for safety)
        new_value: New value (truncated to 100 chars for safety)
        result: Operation result ("success" or "failure")
        details: Additional context (will be logged as structured data)
        ip_address: Client IP address
    """
    audit_entry = {
        "event_type": "SENSITIVE_OPERATION",
        "user_id": user_id,
        "operation": operation,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "result": result,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Truncate sensitive values to prevent log flooding
    if old_value is not None:
        audit_entry["old_value"] = str(old_value)[:100]
    if new_value is not None:
        audit_entry["new_value"] = str(new_value)[:100]
    if details:
        audit_entry["details"] = details
    if ip_address:
        audit_entry["ip_address"] = ip_address

    # Log at INFO level for successful operations, WARNING for failures
    if result == "success":
        audit_logger.info("Sensitive operation completed", **audit_entry)
    else:
        audit_logger.warning("Sensitive operation failed", **audit_entry)


async def log_auth_event(
    user_id: str,
    event_type: str,
    success: bool,
    ip_address: str | None = None,
    details: dict | None = None,
):
    """
    Log authentication events (login, logout, token refresh).

    Args:
        user_id: User ID
        event_type: Type of auth event ("login", "logout", "token_refresh", "token_revoke")
        success: Whether the operation succeeded
        ip_address: Client IP address
        details: Additional context
    """
    await log_sensitive_operation(
        user_id=user_id,
        operation=f"auth_{event_type}",
        resource_type="authentication",
        resource_id=user_id,
        result="success" if success else "failure",
        details=details,
        ip_address=ip_address,
    )


async def log_permission_change(
    user_id: str,
    admin_user_id: str,
    old_role: str,
    new_role: str,
    ip_address: str | None = None,
):
    """
    Log permission/role changes.

    Args:
        user_id: User whose role was changed
        admin_user_id: Admin who made the change
        old_role: Previous role
        new_role: New role
        ip_address: Admin's IP address
    """
    await log_sensitive_operation(
        user_id=admin_user_id,
        operation="role_change",
        resource_type="user_permission",
        resource_id=user_id,
        old_value=old_role,
        new_value=new_role,
        details={"affected_user": user_id},
        ip_address=ip_address,
    )


async def log_report_access(
    user_id: str,
    session_id: str,
    access_type: str,
    ip_address: str | None = None,
):
    """
    Log forensic report access for chain-of-custody.

    Args:
        user_id: User who accessed the report
        session_id: Investigation session ID
        access_type: Type of access ("view", "download", "verify")
        ip_address: Client IP address
    """
    await log_sensitive_operation(
        user_id=user_id,
        operation=f"report_{access_type}",
        resource_type="forensic_report",
        resource_id=session_id,
        result="success",
        ip_address=ip_address,
    )


async def log_signature_verification(
    user_id: str,
    session_id: str,
    signature_valid: bool,
    ip_address: str | None = None,
):
    """
    Log cryptographic signature verification attempts.

    Args:
        user_id: User who requested verification
        session_id: Investigation session ID
        signature_valid: Whether signature is valid
        ip_address: Client IP address
    """
    await log_sensitive_operation(
        user_id=user_id,
        operation="signature_verification",
        resource_type="forensic_report",
        resource_id=session_id,
        result="success" if signature_valid else "failure",
        details={"signature_valid": signature_valid},
        ip_address=ip_address,
    )
