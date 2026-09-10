"""Unit tests for presence service, heartbeat tracking, and offline threshold."""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, DeviceType
from app.models.user import User
from app.services.presence_service import presence_service
from app.services.websocket_manager import ws_manager


@pytest.mark.asyncio
async def test_presence_heartbeat_and_threshold(db_session: AsyncSession):
    # Create user and laptop
    user = User(email="presence_user@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()

    laptop = Device(
        user_id=user.id,
        device_type=DeviceType.LAPTOP.value,
        name="Test Laptop",
    )
    db_session.add(laptop)
    await db_session.commit()

    # Initially, no WebSocket connection exists -> offline
    assert presence_service.is_laptop_online(laptop) is False

    # Simulate WebSocket connection in ws_manager
    ws_manager._connections[laptop.id] = "mock_ws"  # type: ignore

    # With recent heartbeat and active connection -> online
    assert presence_service.is_laptop_online(laptop) is True

    # Simulate heartbeat record update
    updated = await presence_service.record_heartbeat(db_session, laptop.id)
    assert updated is True

    # Simulate stale heartbeat (16 minutes ago, exceeding 15 min threshold)
    laptop.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    assert presence_service.is_laptop_online(laptop) is False

    # Cleanup ws_manager
    if laptop.id in ws_manager._connections:
        del ws_manager._connections[laptop.id]
