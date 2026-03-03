"""
Authentication Routes
=====================

Routes for user authentication and token management.
"""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from core.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    TokenData,
    User,
    UserRole,
    create_access_token,
    get_current_user,
)
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


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


# Demo users - In production, use a database with hashed passwords
# These are for initial setup and testing only
DEMO_USERS = {
    "admin": {
        "user_id": "admin-001",
        "username": "admin",
        "hashed_password": "$2b$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",  # placeholder
        "role": UserRole.ADMIN,
        "disabled": False,
    },
    "investigator": {
        "user_id": "inv-001",
        "username": "investigator",
        "hashed_password": "$2b$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",  # placeholder
        "role": UserRole.INVESTIGATOR,
        "disabled": False,
    },
}


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
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
    # In production, verify against database with proper password hashing
    # For demo, we use a simple check (DO NOT USE IN PRODUCTION)
    from core.auth import verify_password
    
    user = DEMO_USERS.get(form_data.username)
    
    # Demo password check - In production use proper password verification
    # Default passwords for demo:
    #   admin: admin123!
    #   investigator: inv123!
    DEMO_PASSWORDS = {
        "admin": "admin123!",
        "investigator": "inv123!",
    }
    
    if not user or form_data.password != DEMO_PASSWORDS.get(form_data.username):
        logger.warning("Failed login attempt", username=form_data.username)
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
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        user_id=user["user_id"],
        role=user["role"],
        expires_delta=access_token_expires,
    )
    
    logger.info("User logged in successfully", user_id=user["user_id"], role=user["role"].value)
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user["user_id"],
        role=user["role"].value,
    )


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
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        user_id=current_user.user_id,
        role=current_user.role,
        expires_delta=access_token_expires,
    )
    
    logger.info("Token refreshed", user_id=current_user.user_id)
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=current_user.user_id,
        role=current_user.role.value,
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout endpoint.
    
    Note: With JWT tokens, true logout requires token blacklisting.
    In production, add the token to a blacklist (e.g., Redis) until expiry.
    
    Returns:
        Logout confirmation message
    """
    logger.info("User logged out", user_id=current_user.user_id)
    
    # In production: Add token to blacklist in Redis
    # redis_client.setex(f"blacklist:{token}", token_expiry, "true")
    
    return {
        "status": "success",
        "message": "Successfully logged out",
    }
