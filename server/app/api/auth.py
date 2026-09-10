"""Authentication API endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import rate_limiter
from app.core.security import create_access_token, generate_refresh_token, hash_token
from app.models.user import User
from app.schemas.auth import (
    LogoutRequest,
    TokenRefreshRequest,
    TokenRefreshResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: UserRegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Register a new user account with email and password."""
    rate_limiter.check(request)
    user = await auth_service.register_user(session, req.email, req.password)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    req: UserLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Authenticate user and issue initial user access & refresh tokens."""
    rate_limiter.check(request)
    user = await auth_service.authenticate_user(session, req.email, req.password)
    if not user:
        logger.warning("Failed login attempt for email: %s", req.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Issue access token
    access_token = create_access_token(
        user_id=str(user.id),
        device_type="USER",
    )
    raw_refresh = generate_refresh_token()
    # In V1, user can manage pairing and devices
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    req: TokenRefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Refresh an access token using a valid refresh token."""
    rate_limiter.check(request)
    new_access, new_refresh, expires_in = await auth_service.refresh_tokens(
        session=session,
        raw_refresh_token=req.refresh_token,
        device_id=req.device_id,
    )
    return TokenRefreshResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    req: LogoutRequest,
    session: AsyncSession = Depends(get_db),
):
    """Revoke refresh token on client logout."""
    if req.refresh_token:
        await auth_service.revoke_refresh_token(session, req.refresh_token)
    return {"message": "Logged out successfully."}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Retrieve details for currently authenticated user."""
    return current_user
