"""Authentication business logic service."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.device import Device
from app.models.refresh_token import RefreshToken
from app.models.user import User

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthService:
    """Handles user registration, credential validation, and JWT/refresh token lifecycle."""

    @staticmethod
    async def register_user(
        session: AsyncSession, email: str, password: str
    ) -> User:
        """Register a new user account."""
        clean_email = email.strip().lower()
        stmt = select(User).where(User.email == clean_email)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email address already exists.",
            )

        hashed = hash_password(password)
        user = User(email=clean_email, password_hash=hashed)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info("Registered new user: %s (id: %s)", clean_email, user.id)
        return user

    @staticmethod
    async def authenticate_user(
        session: AsyncSession, email: str, password: str
    ) -> Optional[User]:
        """Authenticate user credentials."""
        clean_email = email.strip().lower()
        stmt = select(User).where(User.email == clean_email)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            return None

        if not verify_password(password, user.password_hash):
            return None

        return user

    @staticmethod
    async def create_tokens_for_device(
        session: AsyncSession,
        user_id: uuid.UUID,
        device_id: uuid.UUID,
        device_type: str,
    ) -> Tuple[str, str, int]:
        """Generate JWT access token and persist a new refresh token for device."""
        access_token = create_access_token(
            user_id=str(user_id),
            device_id=str(device_id),
            device_type=device_type,
        )

        raw_refresh_token = generate_refresh_token()
        refresh_hash = hash_token(raw_refresh_token)

        expires_at = utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        refresh_record = RefreshToken(
            user_id=user_id,
            device_id=device_id,
            token_hash=refresh_hash,
            expires_at=expires_at,
        )
        session.add(refresh_record)
        await session.commit()

        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return access_token, raw_refresh_token, expires_in

    @staticmethod
    async def refresh_tokens(
        session: AsyncSession,
        raw_refresh_token: str,
        device_id: Optional[uuid.UUID] = None,
    ) -> Tuple[str, str, int]:
        """Validate refresh token and issue a fresh access token."""
        refresh_hash = hash_token(raw_refresh_token)
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.token_hash == refresh_hash)
            .where(RefreshToken.revoked_at.is_(None))
        )
        token_record = (await session.execute(stmt)).scalar_one_or_none()

        if not token_record or not token_record.is_valid:
            logger.warning("Token refresh failed: token is expired or revoked.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token.",
            )

        if device_id and token_record.device_id != device_id:
            logger.warning("Token refresh device mismatch: %s != %s", token_record.device_id, device_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token device mismatch.",
            )

        # Check device is not revoked
        dev_stmt = select(Device).where(Device.id == token_record.device_id)
        device = (await session.execute(dev_stmt)).scalar_one_or_none()
        if not device or not device.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Device has been revoked or removed.",
            )

        # Issue fresh access token
        new_access_token = create_access_token(
            user_id=str(token_record.user_id),
            device_id=str(token_record.device_id),
            device_type=device.device_type,
        )

        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        # Preserve existing valid refresh token
        return new_access_token, raw_refresh_token, expires_in

    @staticmethod
    async def revoke_refresh_token(
        session: AsyncSession, raw_refresh_token: str
    ) -> bool:
        """Revoke a refresh token on logout."""
        refresh_hash = hash_token(raw_refresh_token)
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.token_hash == refresh_hash)
            .values(revoked_at=utcnow())
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0


auth_service = AuthService()
