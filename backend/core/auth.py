"""
Authentication and Authorization Module
=======================================

JWT-based authentication using FastAPI security utilities.
Provides token generation, validation, and dependency injection for protected routes.
"""

import warnings
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# Suppress passlib warning about bcrypt.__version__ attribute removed in bcrypt>=4.0
warnings.filterwarnings("ignore", ".*error reading bcrypt version.*", UserWarning)

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

# JWT Configuration - Loaded from settings for persistence across rebuilds
settings = get_settings()
SECRET_KEY = settings.effective_jwt_secret
ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.jwt_access_token_expire_minutes  # Default: 60 minutes

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
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": user_id,
        "username": username or user_id,
        "role": role.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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


async def is_token_blacklisted(token: str) -> bool:
    """
    Check if a token is blacklisted.
    
    Args:
        token: JWT token string
    
    Returns:
        True if token is blacklisted, False otherwise
    
    NOTE: Fail-open design — if Redis is unavailable we allow the request
    through with a warning rather than denying ALL authenticated users.
    The JWT signature + expiry claims still provide validity guarantees
    even without the blacklist. This is a deliberate trade-off: a brief
    Redis outage should not cause a service outage.
    """
    try:
        from infra.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            result = await redis.get(f"blacklist:{token}")
            return result is not None
        else:
            logger.warning("Redis unavailable — token blacklist check skipped, proceeding with JWT claims only")
            return False
    except Exception as e:
        logger.warning("Redis unavailable — token blacklist check skipped, proceeding with JWT claims only", error=str(e))
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
            await redis.set(f"blacklist:{token}", "1", ex=expires_in_seconds)
            logger.info("Token blacklisted", expires_in=expires_in_seconds)
    except Exception as e:
        logger.warning("Failed to blacklist token", error=str(e))


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    
    Args:
        credentials: HTTP Bearer credentials
    
    Returns:
        Authenticated User object
    
    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
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
        return await get_current_user(credentials)
    except HTTPException:
        return None
