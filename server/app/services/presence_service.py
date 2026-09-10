"""Presence tracking service for laptop connectivity and heartbeat beacons."""

from datetime import datetime, timedelta, timezone
import logging
from typing import List
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.device import Device, DeviceType
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PresenceService:
    """Tracks and evaluates whether laptop clients are online and reachable."""

    @staticmethod
    async def record_heartbeat(session: AsyncSession, device_id: uuid.UUID) -> bool:
        """Update last_seen_at timestamp for device."""
        now = utcnow()
        stmt = (
            update(Device)
            .where(Device.id == device_id)
            .where(Device.revoked_at.is_(None))
            .values(last_seen_at=now)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    def is_laptop_online(device: Device) -> bool:
        """Evaluate if laptop is currently online.
        
        Requires:
        1. Device not revoked
        2. Active WebSocket connection exists
        3. Heartbeat received within LAPTOP_OFFLINE_SECONDS (default 15 minutes)
        """
        if not device.is_active:
            return False

        if not ws_manager.is_connected(device.id):
            return False

        cutoff = utcnow() - timedelta(seconds=settings.LAPTOP_OFFLINE_SECONDS)
        # Handle timezone-aware/naive comparison cleanly
        last_seen = device.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        return last_seen >= cutoff

    @staticmethod
    async def get_online_laptops_for_user(
        session: AsyncSession, user_id: uuid.UUID
    ) -> List[Device]:
        """Fetch all active laptops for user and return those currently online."""
        stmt = (
            select(Device)
            .where(Device.user_id == user_id)
            .where(Device.device_type == DeviceType.LAPTOP.value)
            .where(Device.revoked_at.is_(None))
        )
        result = await session.execute(stmt)
        laptops = result.scalars().all()

        online_laptops = [laptop for laptop in laptops if PresenceService.is_laptop_online(laptop)]
        logger.debug(
            "User %s has %d total laptop(s), %d online",
            user_id,
            len(laptops),
            len(online_laptops),
        )
        return online_laptops


presence_service = PresenceService()
