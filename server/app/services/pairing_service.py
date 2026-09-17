"""Pairing business logic service for authenticating new laptops and devices."""

from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Optional, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_pairing_code, hash_pairing_code
from app.models.device import Device, DeviceType
from app.models.pairing import PairingCode
from app.models.user import User
from app.services.auth_service import auth_service

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PairingService:
    """Manages short-lived pairing code generation and single-use claiming."""

    @staticmethod
    async def generate_laptop_pairing(
        session: AsyncSession,
        device_name: Optional[str] = None,
        platform: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Tuple[str, datetime, int, Device, str, str]:
        """Generate a pairing code requested by a laptop client.
        
        Creates/identifies the User, registers the Laptop Device, issues tokens,
        and generates a 6-character PairingCode for phone claiming.
        """
        # 1. Resolve or create user
        if user_id:
            stmt = select(User).where(User.id == user_id)
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User associated with token not found.",
                )
        else:
            guest_email = f"user_{uuid.uuid4().hex[:12]}@noinsta.internal"
            random_pw = secrets.token_urlsafe(32)
            user = await auth_service.register_user(
                session=session,
                email=guest_email,
                password=random_pw,
            )

        # 2. Register laptop device
        clean_name = (device_name or "Laptop").strip()
        device = Device(
            user_id=user.id,
            device_type=DeviceType.LAPTOP.value,
            name=clean_name,
        )
        session.add(device)
        await session.commit()
        await session.refresh(device)

        # 3. Issue device credentials for laptop
        access_token, refresh_token, _ = await auth_service.create_tokens_for_device(
            session=session,
            user_id=device.user_id,
            device_id=device.id,
            device_type=device.device_type,
        )

        # 4. Generate 6-character pairing code
        raw_code, expires_at, expires_in_seconds = await PairingService.create_pairing_code(
            session=session,
            user_id=device.user_id,
        )

        logger.info(
            "Generated pairing code %s for laptop %s (device_id: %s, user_id: %s)",
            raw_code,
            device.name,
            device.id,
            device.user_id,
        )

        return raw_code, expires_at, expires_in_seconds, device, access_token, refresh_token

    @staticmethod
    async def get_pairing_status(
        session: AsyncSession, raw_code: str
    ) -> Tuple[bool, bool, Optional[str], datetime, bool]:
        """Check status of pairing code.
        Returns: (exists: bool, is_claimed: bool, claimed_device_name: Optional[str], expires_at: datetime, is_expired: bool)
        """
        code_hash = hash_pairing_code(raw_code)
        stmt = select(PairingCode).where(PairingCode.code_hash == code_hash)
        pairing_record = (await session.execute(stmt)).scalar_one_or_none()
        if not pairing_record:
            return False, False, None, utcnow(), True

        is_claimed = pairing_record.used_at is not None
        claimed_device_name = None
        if is_claimed:
            stmt_dev = (
                select(Device)
                .where(Device.user_id == pairing_record.user_id)
                .where(Device.device_type == DeviceType.ANDROID.value)
                .order_by(Device.created_at.desc())
            )
            android_dev = (await session.execute(stmt_dev)).scalars().first()
            if android_dev:
                claimed_device_name = android_dev.name

        is_expired = False
        return True, is_claimed, claimed_device_name, pairing_record.expires_at, is_expired


    @staticmethod
    async def create_pairing_code(
        session: AsyncSession, user_id: uuid.UUID
    ) -> Tuple[str, datetime, int]:
        """Generate a secure, single-use 6-character pairing code for user."""
        raw_code = generate_pairing_code(length=6)
        code_hash = hash_pairing_code(raw_code)

        expires_in_seconds = settings.PAIRING_CODE_EXPIRE_MINUTES * 60
        expires_at = utcnow() + timedelta(seconds=expires_in_seconds)

        pairing_record = PairingCode(
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
        )
        session.add(pairing_record)
        await session.commit()

        logger.info("Generated new pairing code for user %s (expires: %s)", user_id, expires_at)
        return raw_code, expires_at, expires_in_seconds

    @staticmethod
    async def claim_pairing_code(
        session: AsyncSession,
        raw_code: str,
        device_name: str,
        device_type: Optional[str] = "LAPTOP",
        platform: Optional[str] = None,
    ) -> Tuple[Device, str, str]:
        """Validate pairing code, register device, and issue permanent device credentials."""
        code_hash = hash_pairing_code(raw_code)

        stmt = select(PairingCode).where(PairingCode.code_hash == code_hash)
        pairing_record = (await session.execute(stmt)).scalar_one_or_none()

        if not pairing_record:
            logger.warning("Pairing attempt with non-existent code.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired pairing code.",
            )

        # Increment attempt counter
        pairing_record.attempt_count += 1

        if not pairing_record.is_valid:
            await session.commit()
            logger.warning("Pairing attempt with invalid/expired/used code.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid, expired, or previously used pairing code.",
            )

        # Mark code as consumed immediately
        pairing_record.used_at = utcnow()

        # Validate device type
        normalized_type = (device_type or "LAPTOP").strip().upper()
        if normalized_type not in (DeviceType.LAPTOP.value, DeviceType.ANDROID.value):
            normalized_type = DeviceType.LAPTOP.value

        # Create Device record
        device = Device(
            user_id=pairing_record.user_id,
            device_type=normalized_type,
            name=device_name.strip() or f"Device-{raw_code[:3]}",
        )
        session.add(device)
        await session.commit()
        await session.refresh(device)

        # Generate tokens
        access_token, refresh_token, _ = await auth_service.create_tokens_for_device(
            session=session,
            user_id=device.user_id,
            device_id=device.id,
            device_type=device.device_type,
        )

        logger.info(
            "Device successfully paired: %s (id: %s, type: %s, user: %s)",
            device.name,
            device.id,
            device.device_type,
            device.user_id,
        )
        return device, access_token, refresh_token


pairing_service = PairingService()
