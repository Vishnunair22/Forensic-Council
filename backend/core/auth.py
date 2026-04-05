"""
Authentication and Authorization Module
=======================================

JWT-based authentication using FastAPI security utilities.
Provides token generation, validation, and dependency injection for protected routes.
"""

import hashlib
import warnings
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from core.config import get_settings
from core.structured_logging import get_logger

# Suppress passlib warning about bcrypt.__version__ attribute removed in bcrypt>=4.0
warnings.filterwarnings("ignore", ".*error reading bcrypt version.*", UserWarning)

logger = get_logger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# Security scheme for Swagger UI
security = HTTPBearer(
    scheme_name="JWT",
    description="Enter your JWT token",
    auto_error=True,
)

# Separate scheme for optional auth (doesn't raise error if no token)
security_optional = HTTPBearer(
    scheme_name="JWT",
    description="Enter your JWT token (optional)",
    auto_error=False,
)


class UserRole(str, Enum):
    """User roles for role-based access control."""

    INVESTIGATOR = "investigator"
    ADMIN = "admin"
    AUDITOR = "auditor"


class TokenData(BaseModel):
    """Token payload data."""

    user_id: str
    username: str
    role: UserRole
    exp: Optional[datetime] = None


class User(BaseModel):
    """User model for authentication."""

    user_id: str
    username: str
    role: UserRole
    disabled: bool = False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash. Truncates to 72 bytes for bcrypt compatibility."""
    # bcrypt has a 72-byte limit; truncate if necessary
    if len(plain_password.encode("utf-8")) > 72:
        plain_password = plain_password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash. Truncates to 72 bytes for bcrypt compatibility."""
    # bcrypt has a 72-byte limit; truncate if necessary
    if len(password.encode("utf-8")) > 72:
        password = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return pwd_context.hash(password)


def create_access_token(
    user_id: str,
    role: UserRole,
    expires_delta: Optional[timedelta] = None,
    username: Optional[str] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: Unique user identifier
        role: User role for authorization
        expires_delta: Token expiration time

    Returns:
        Encoded JWT token
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        _settings = get_settings()
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=_settings.jwt_access_token_expire_minutes
        )

    to_encode = {
        "sub": user_id,
        "username": username or user_id,
        "role": role.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    _settings = get_settings()
    encoded_jwt = jwt.encode(
        to_encode, _settings.effective_jwt_secret, algorithm=_settings.jwt_algorithm
    )
    logger.info(
        "Created access token",
        user_id=user_id,
        role=role.value,
        expires=expire.isoformat(),
    )
    return encoded_jwt


async def decode_token(token: str) -> TokenData:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token data

    Raises:
        HTTPException: If token is invalid or expired
    """
    # Check if token is blacklisted
    if await is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        _settings = get_settings()
        payload = jwt.decode(
            token, _settings.effective_jwt_secret, algorithms=[_settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        username: str = payload.get("username", user_id)
        role_str: str = payload.get("role")
        exp = payload.get("exp")

        if user_id is None or role_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        role = UserRole(role_str)
        exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None

        return TokenData(
            user_id=user_id, username=username, role=role, exp=exp_datetime
        )

    except JWTError as e:
        logger.warning("JWT decode error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Local in-memory cache for recently blacklisted tokens (fallback during Redis outages)
# This provides a safety net when Redis is unavailable
_recently_blacklisted: dict[str, float] = {}  # token_hash -> expiry_timestamp
_LOCAL_BLACKLIST_MAX_AGE = 3600  # 1 hour max age for local blacklist entries
_LOCAL_BLACKLIST_MAX_SIZE = 10000  # prevent unbounded memory growth

# Persistent SQLite cache for token blacklist (survives Redis outages and container restarts)
_blacklist_db_path: Optional[str] = None


def _get_blacklist_db_path() -> str:
    """Get path to SQLite blacklist database."""
    global _blacklist_db_path
    if _blacklist_db_path is None:
        from core.config import get_settings
        settings = get_settings()
        storage_dir = Path(getattr(settings, "storage_dir", "/tmp/forensic_storage"))
        storage_dir.mkdir(parents=True, exist_ok=True)
        _blacklist_db_path = str(storage_dir / "token_blacklist.db")
    return _blacklist_db_path


def _init_blacklist_db():
    """Initialize SQLite database for persistent token blacklist."""
    import sqlite3
    
    db_path = _get_blacklist_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blacklisted_tokens (
            token_hash TEXT PRIMARY KEY,
            expires_at REAL NOT NULL,
            created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON blacklisted_tokens(expires_at)")
    conn.commit()
    return conn


def _add_to_persistent_blacklist(token_hash: str, expires_at: float):
    """Add token hash to persistent SQLite blacklist."""
    try:
        conn = _init_blacklist_db()
        conn.execute(
            "INSERT OR REPLACE INTO blacklisted_tokens (token_hash, expires_at) VALUES (?, ?)",
            (token_hash, expires_at)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to persist token blacklist entry", error=str(e))


def _is_in_persistent_blacklist(token_hash: str) -> bool:
    """Check if token hash is in persistent SQLite blacklist."""
    try:
        import time
        conn = _init_blacklist_db()
        cursor = conn.execute(
            "SELECT expires_at FROM blacklisted_tokens WHERE token_hash = ?",
            (token_hash,)
        )
        row = cursor.fetchone()
        
        if row:
            expires_at = row[0]
            if time.time() < expires_at:
                conn.close()
                return True
            else:
                # Expired - remove it
                conn.execute("DELETE FROM blacklisted_tokens WHERE token_hash = ?", (token_hash,))
                conn.commit()
        conn.close()
        return False
    except Exception as e:
        logger.warning("Failed to check persistent blacklist", error=str(e))
        return False


def _cleanup_expired_blacklist_entries():
    """Remove expired entries from persistent blacklist."""
    try:
        import time
        conn = _init_blacklist_db()
        conn.execute("DELETE FROM blacklisted_tokens WHERE expires_at < ?", (time.time(),))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to cleanup expired blacklist entries", error=str(e))


def _cleanup_local_blacklist() -> None:
    """Remove expired entries from local blacklist cache."""
    import time

    current_time = time.time()
    # Build list of expired keys first, then delete (safe iteration)
    expired_keys = [k for k, v in _recently_blacklisted.items() if current_time > v]
    for k in expired_keys:
        _recently_blacklisted.pop(k, None)
    # Enforce max size by dropping oldest entries if needed
    if len(_recently_blacklisted) > _LOCAL_BLACKLIST_MAX_SIZE:
        sorted_items = sorted(_recently_blacklisted.items(), key=lambda item: item[1])
        for k, _ in sorted_items[
            : len(_recently_blacklisted) - _LOCAL_BLACKLIST_MAX_SIZE
        ]:
            _recently_blacklisted.pop(k, None)


async def is_token_blacklisted(token: str) -> bool:
    """
    Check if a token is blacklisted.

    Args:
        token: JWT token string

    Returns:
        True if token is blacklisted, False otherwise

    SECURITY FIX: Fail-secure design with local cache fallback.
    - Primary: Check Redis blacklist
    - Fallback: Check local in-memory cache
    - If both unavailable in PRODUCTION: Reject the token (fail-secure)
    - If both unavailable in DEVELOPMENT: Allow with warning (for dev convenience)

    This prevents revoked tokens from being used during Redis outages.
    """
    import time
    import hashlib

    # Create a hash of the token for local storage (don't store raw tokens)
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:32]

    # Cleanup old entries periodically
    _cleanup_local_blacklist()

    # Check local cache first (fast path for known blacklisted tokens)
    if token_hash in _recently_blacklisted:
        expiry = _recently_blacklisted[token_hash]
        if time.time() < expiry:
            return True
        else:
            # Expired, remove it
            _recently_blacklisted.pop(token_hash, None)

    try:
        from infra.redis_client import get_redis_client

        redis = await get_redis_client()

        if redis:
            result = await redis.get(f"blacklist:{token_hash}")
            if result is not None:
                # Also cache locally for future lookups during Redis outages
                # Default to 1 hour if we don't know the exact expiry
                _recently_blacklisted[token_hash] = (
                    time.time() + _LOCAL_BLACKLIST_MAX_AGE
                )
                return True
            return False
        else:
            # Redis unavailable - check if we have it in local cache
            if token_hash in _recently_blacklisted:
                return True

            # Fail-secure in production: if Redis is down and we don't have a local record,
            # we can't verify the token isn't blacklisted. In production, reject.
            # In development, allow for convenience.
            if get_settings().app_env == "production":
                logger.error(
                    "Redis unavailable in production — token blacklist check FAILING SECURE. "
                    "Token rejected because blacklist cannot be verified."
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service temporarily unavailable. Please try again.",
                )
            else:
                logger.warning(
                    "Redis unavailable in development — token blacklist check skipped, "
                    "proceeding with JWT claims only (fail-open for dev convenience)"
                )
                return False

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Redis error during blacklist check", error=str(e))

        # Check local cache as fallback
        if token_hash in _recently_blacklisted:
            return True
        
        # Check persistent SQLite blacklist as second fallback
        if _is_in_persistent_blacklist(token_hash):
            # Also add to local cache for faster future lookups
            _recently_blacklisted[token_hash] = time.time() + _LOCAL_BLACKLIST_MAX_AGE
            return True

        # Fail-secure in production - reject tokens we can't verify
        if get_settings().app_env == "production":
            logger.error(
                "Redis unavailable in production — token blacklist check FAILING SECURE. "
                "Token rejected because blacklist cannot be verified."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable. Please try again.",
            )
        else:
            logger.warning(
                "Redis unavailable in development — token blacklist check skipped, "
                "proceeding with JWT claims only (fail-open for dev convenience)"
            )
            return False


async def blacklist_token(token: str, expires_in_seconds: int) -> None:
    """
    Add a token to the blacklist.

    Args:
        token: JWT token string
        expires_in_seconds: How long to keep the token blacklisted
    """
    try:
        from infra.redis_client import get_redis_client

        redis = await get_redis_client()
        if redis:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            await redis.set(f"blacklist:{token_hash}", "1", ex=expires_in_seconds)
            logger.info("Token blacklisted", expires_in=expires_in_seconds)
    except Exception as e:
        logger.warning("Failed to blacklist token", error=str(e))


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    Checks Authorization header first, then falls back to 'access_token' cookie.
    """
    token = None
    if credentials:
        token = credentials.credentials
    else:
        # Fallback to HttpOnly cookie for production-hardened XSS protection
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = await decode_token(token)

    # In production, fetch user from database
    try:
        from infra.postgres_client import get_postgres_client

        postgres = await get_postgres_client()
        if postgres:
            query = "SELECT is_disabled FROM users WHERE user_id = $1"
            row = await postgres.fetch_one(query, token_data.user_id)
            if row and row.get("is_disabled"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is disabled",
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to verify account status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    user = User(
        user_id=token_data.user_id,
        username=token_data.username,
        role=token_data.role,
    )

    return user


def require_role(required_role: UserRole):
    """
    Dependency factory to require a specific role.

    Args:
        required_role: The role required for access

    Returns:
        Dependency function that validates user role
    """

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role.value}",
            )
        return current_user

    return role_checker


# Common role-based dependencies
require_admin = require_role(UserRole.ADMIN)
require_investigator = require_role(UserRole.INVESTIGATOR)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
) -> Optional[User]:
    """
    Dependency to optionally get the current user (allows anonymous access).

    Args:
        credentials: Optional HTTP Bearer credentials

    Returns:
        User object if authenticated, None otherwise
    """
    if not credentials:
        return None

    try:
        token_data = await decode_token(credentials.credentials)
        return User(
            user_id=token_data.user_id,
            username=token_data.username,
            role=token_data.role,
        )
    except HTTPException:
        return None
