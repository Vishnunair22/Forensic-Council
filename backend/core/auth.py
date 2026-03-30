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
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# Suppress passlib warning about bcrypt.__version__ attribute removed in bcrypt>=4.0
warnings.filterwarnings("ignore", ".*error reading bcrypt version.*", UserWarning)

from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
    """Verify a password against its hash."""
    # Truncate password to 72 bytes to avoid bcrypt library bug with passlib
    return pwd_context.verify(plain_password[:72], hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
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
        expire = datetime.now(timezone.utc) + timedelta(minutes=_settings.jwt_access_token_expire_minutes)
    
    to_encode = {
        "sub": user_id,
        "username": username or user_id,
        "role": role.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    
    _settings = get_settings()
    encoded_jwt = jwt.encode(to_encode, _settings.effective_jwt_secret, algorithm=_settings.jwt_algorithm)
    logger.info("Created access token", user_id=user_id, role=role.value, expires=expire.isoformat())
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
        payload = jwt.decode(token, _settings.effective_jwt_secret, algorithms=[_settings.jwt_algorithm])
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
        
        return TokenData(user_id=user_id, username=username, role=role, exp=exp_datetime)
    
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


def _cleanup_local_blacklist() -> None:
    """Remove expired entries from local blacklist cache."""
    import time
    current_time = time.time()
    # Build list of expired keys first, then delete (safe iteration)
    expired_keys = [
        k for k, v in _recently_blacklisted.items()
        if current_time > v
    ]
    for k in expired_keys:
        _recently_blacklisted.pop(k, None)
    # Enforce max size by dropping oldest entries if needed
    if len(_recently_blacklisted) > _LOCAL_BLACKLIST_MAX_SIZE:
        sorted_items = sorted(_recently_blacklisted.items(), key=lambda item: item[1])
        for k, _ in sorted_items[:len(_recently_blacklisted) - _LOCAL_BLACKLIST_MAX_SIZE]:
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
                _recently_blacklisted[token_hash] = time.time() + _LOCAL_BLACKLIST_MAX_AGE
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
        
        # Fail-secure in production
        if get_settings().app_env == "production":
            logger.error(
                "Redis error in production — token blacklist check FAILING SECURE. "
                "Token rejected because blacklist cannot be verified."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable. Please try again.",
            )
        else:
            logger.warning(
                "Redis error in development — token blacklist check skipped, "
                "proceeding with JWT claims only"
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
        logger.warning("Failed to check database for disabled user", error=str(e))
    
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
