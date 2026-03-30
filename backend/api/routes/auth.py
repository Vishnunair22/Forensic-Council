"""
Authentication Routes
=====================

Routes for user authentication and token management.
"""

import time
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from core.auth import (
    User,
    UserRole,
    create_access_token,
    get_current_user,
)
from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

# ── Brute-force login protection ─────────────────────────────────────────────
# Per-IP attempt tracking with a sliding window.
# Redis is used when available; falls back to an in-process dict.
_MAX_LOGIN_ATTEMPTS = 5        # max failures before lockout
_LOCKOUT_WINDOW_SECS = 300     # 5-minute rolling window
_LOCKOUT_DURATION_SECS = 900   # 15-minute lockout

# In-memory fallback: {ip: [(timestamp, count), ...]}
_failed_attempts: dict[str, list[float]] = defaultdict(list)


async def _is_rate_limited(ip: str) -> bool:
    """Return True and raise 429 if the IP has exceeded the login attempt limit."""
    key = f"login_fail:{ip}"
    now = time.time()

    try:
        from infra.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            count_raw = await redis.get(key)
            count = int(count_raw) if count_raw else 0
            if count >= _MAX_LOGIN_ATTEMPTS:
                ttl = await redis.ttl(key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed login attempts. Try again in {max(ttl, 1)} seconds.",
                    headers={"Retry-After": str(max(ttl, 1))},
                )
            return False
    except HTTPException:
        raise
    except Exception as e:
        # FAIL-SECURE: If Redis is configured but unreachable for an auth endpoint,
        # we MUST DENY access rather than falling back to in-memory, to prevent
        # multi-worker brute-force bypass.  Only skip if Redis is truly not configured.
        if settings.redis_host != "localhost" or settings.app_env == "production":
            logger.error("Redis unreachable for rate limiting - failing secure on auth", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Security validation service unavailable. Please retry later.",
            )
        pass  # allow local fallback in dev only

    # In-memory fallback — prune old entries outside the window
    attempts = _failed_attempts[ip]
    cutoff = now - _LOCKOUT_WINDOW_SECS
    attempts[:] = [t for t in attempts if t > cutoff]
    if len(attempts) >= _MAX_LOGIN_ATTEMPTS:
        retry_after = int(_LOCKOUT_WINDOW_SECS - (now - attempts[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Try again in {max(retry_after, 1)} seconds.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )
    return False


async def _record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt for the given IP."""
    key = f"login_fail:{ip}"
    try:
        from infra.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, _LOCKOUT_DURATION_SECS)
            await pipe.execute()
            return
    except Exception:
        pass
    _failed_attempts[ip].append(time.time())


async def _clear_failed_attempts(ip: str) -> None:
    """Clear failed attempts on successful login."""
    key = f"login_fail:{ip}"
    try:
        from infra.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            await redis.delete(key)
            return
    except Exception:
        pass
    _failed_attempts.pop(ip, None)



class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: str


class UserResponse(BaseModel):
    """User information response."""
    user_id: str
    username: str
    role: str


# ── Development-only fallback user store ──────────────────────────────────────
# Used ONLY when:
#   a) app_env != "production"  AND
#   b) the database is unavailable
#
# Passwords are loaded from environment variables at runtime — no credentials
# are baked into the binary.  In production the database is the sole authority.
#
# To set passwords: export BOOTSTRAP_ADMIN_PASSWORD and BOOTSTRAP_INVESTIGATOR_PASSWORD
# (already documented in .env.example).  These are the same variables used by
# scripts/init_db.py to bootstrap the users table.
import os as _os

# Only load demo credentials in non-production environments
_settings = get_settings()
if _settings.app_env != "production":
    _DEV_ADMIN_PASSWORD    = _os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    _DEV_INV_PASSWORD      = _os.environ.get("BOOTSTRAP_INVESTIGATOR_PASSWORD", "")
else:
    _DEV_ADMIN_PASSWORD    = ""
    _DEV_INV_PASSWORD      = ""


def _build_dev_fallback() -> dict:
    """Build dev fallback dict from env vars. Returns empty dict in production or if passwords not set."""
    if not _DEV_ADMIN_PASSWORD and not _DEV_INV_PASSWORD:
        return {}
    from passlib.context import CryptContext as _CC
    _ctx = _CC(schemes=["bcrypt"], deprecated="auto")
    users: dict = {}
    if _DEV_ADMIN_PASSWORD:
        users["admin"] = {
            "user_id": "admin-dev-001",
            "username": "admin",
            "hashed_password": _ctx.hash(_DEV_ADMIN_PASSWORD),
            "role": UserRole.ADMIN,
            "disabled": False,
        }
    if _DEV_INV_PASSWORD:
        users["investigator"] = {
            "user_id": "inv-dev-001",
            "username": "investigator",
            "hashed_password": _ctx.hash(_DEV_INV_PASSWORD),
            "role": UserRole.INVESTIGATOR,
            "disabled": False,
        }
    return users


# Built once at import time — avoids re-hashing on every request
_DEMO_USERS_FALLBACK: dict = _build_dev_fallback()


async def get_user_from_db(username: str) -> Optional[dict]:
    """Fetch user from PostgreSQL database."""
    from infra.postgres_client import get_postgres_client
    try:
        client = await get_postgres_client()
        row = await client.fetch_one(
            "SELECT user_id, username, hashed_password, role, is_disabled "
            "FROM users WHERE username = $1 AND is_active = TRUE",
            username
        )
        if row:
            return {
                "user_id": row["user_id"],
                "username": row["username"],
                "hashed_password": row["hashed_password"],
                "role": UserRole(row["role"]),
                "disabled": row["is_disabled"],
            }
    except Exception as e:
        logger.warning("Database unavailable, using fallback auth", error=str(e))
    return None


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate user and return JWT token.
    
    Accepts standard OAuth2 password flow credentials.
    Returns a JWT access token for subsequent authenticated requests.
    
    Args:
        form_data: OAuth2 password request form with username and password
    
    Returns:
        TokenResponse with access token and user information
    
    Raises:
        HTTPException: If authentication fails
    """
    # Verify password using bcrypt
    from core.auth import verify_password
    
    # Rate-limit check before any database work
    client_ip = request.client.host if request.client else "unknown"
    await _is_rate_limited(client_ip)

    # Try to fetch user from database first
    user = await get_user_from_db(form_data.username)
    
    # Fallback to demo users if database is unavailable (strictly non-production)
    if not user and settings.app_env != "production":
        user = _DEMO_USERS_FALLBACK.get(form_data.username)
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        await _record_failed_attempt(client_ip)
        logger.warning("Failed login attempt", username=form_data.username, ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user["disabled"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    
    access_token_expires = timedelta(minutes=get_settings().jwt_access_token_expire_minutes)
    access_token = create_access_token(
        user_id=user["user_id"],
        role=user["role"],
        expires_delta=access_token_expires,
        username=user["username"],
    )
    
    await _clear_failed_attempts(client_ip)
    logger.info("User logged in successfully", user_id=user["user_id"], role=user["role"].value)
    
    response = JSONResponse(
        content=TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=get_settings().jwt_access_token_expire_minutes * 60,
            user_id=user["user_id"],
            role=user["role"].value,
        ).model_dump()
    )
    
    # Set HttpOnly cookie for production-hardened XSS protection
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=get_settings().jwt_access_token_expire_minutes * 60,
        expires=get_settings().jwt_access_token_expire_minutes * 60,
        samesite="strict",
        secure=True if settings.app_env == "production" else False,
    )
    
    return response


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information.
    
    Returns:
        UserResponse with user details
    """
    return UserResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        role=current_user.role.value,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(current_user: User = Depends(get_current_user)):
    """
    Refresh the access token.
    
    Returns a new access token with extended expiration.
    
    Returns:
        TokenResponse with new access token
    """
    access_token_expires = timedelta(minutes=get_settings().jwt_access_token_expire_minutes)
    access_token = create_access_token(
        user_id=current_user.user_id,
        role=current_user.role,
        expires_delta=access_token_expires,
        username=current_user.username,
    )
    
    logger.info("Token refreshed", user_id=current_user.user_id)
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=get_settings().jwt_access_token_expire_minutes * 60,
        user_id=current_user.user_id,
        role=current_user.role.value,
    )


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    authorization: Optional[str] = Header(None)
):
    """
    Logout endpoint.
    
    Adds the JWT token to a blacklist in Redis until it expires.
    
    Returns:
        Logout confirmation message
    """
    from core.auth import blacklist_token, decode_token
    
    # Extract token from Authorization header
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    
    # Blacklist the token if we have it
    if token:
        try:
            # Get token expiry to set blacklist TTL
            token_data = await decode_token(token)
            if token_data.exp:
                import time
                expires_in = int(token_data.exp.timestamp() - time.time())
                if expires_in > 0:
                    await blacklist_token(token, expires_in)
                    logger.info("Token blacklisted on logout", user_id=current_user.user_id)
        except Exception as e:
            logger.warning("Failed to blacklist token on logout", error=str(e))
    
    logger.info("User logged out", user_id=current_user.user_id)
    
    response = JSONResponse(content={
        "status": "success",
        "message": "Successfully logged out",
    })
    response.delete_cookie("access_token")
    return response
