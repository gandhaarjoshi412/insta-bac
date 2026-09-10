"""Integration tests for WebSocket laptop connection, authentication, and heartbeats."""

import json
import os
import uuid
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.core.database import Base, async_session_factory, engine
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.device import Device, DeviceType
from app.models.user import User


def test_websocket_authentication_and_heartbeat():
    """Test full WebSocket handshake, authentication, and heartbeat flow."""
    import asyncio

    test_db_file = Path(f"test_ws_{uuid.uuid4().hex[:8]}.db")

    async def setup_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with async_session_factory() as session:
            user = User(email=f"ws_{uuid.uuid4().hex[:6]}@example.com", password_hash="hash")
            session.add(user)
            await session.flush()

            laptop = Device(
                user_id=user.id,
                device_type=DeviceType.LAPTOP.value,
                name="Test Laptop",
            )
            session.add(laptop)
            await session.commit()
            return str(user.id), str(laptop.id)

    user_id, device_id = asyncio.run(setup_db())

    # Generate valid access token for laptop
    token = create_access_token(
        user_id=user_id,
        device_id=device_id,
        device_type=DeviceType.LAPTOP.value,
    )

    with TestClient(fastapi_app) as client:
        # 1. Connect to WebSocket
        with client.websocket_connect(f"/ws/device/{device_id}") as websocket:
            # 2. Send authentication message
            auth_msg = {
                "type": "authenticate",
                "access_token": token,
                "device_id": device_id,
            }
            websocket.send_text(json.dumps(auth_msg))

            # 3. Receive authenticated confirmation
            auth_resp = json.loads(websocket.receive_text())
            assert auth_resp["type"] == "authenticated"
            assert auth_resp["device_id"] == device_id
            assert auth_resp["user_id"] == user_id

            # 4. Send heartbeat message
            hb_msg = {
                "type": "heartbeat",
                "device_id": device_id,
            }
            websocket.send_text(json.dumps(hb_msg))

            # 5. Receive heartbeat_ack
            hb_ack = json.loads(websocket.receive_text())
            assert hb_ack["type"] == "heartbeat_ack"

            # 6. Send intervention_closed message
            closed_msg = {
                "type": "intervention_closed",
                "event_id": str(uuid.uuid4()),
                "device_id": device_id,
            }
            websocket.send_text(json.dumps(closed_msg))


def test_websocket_invalid_token_rejection():
    """Test that invalid authentication is rejected and closes connection."""
    with TestClient(fastapi_app) as client:
        with client.websocket_connect("/ws/laptop") as websocket:
            auth_msg = {
                "type": "authenticate",
                "access_token": "completely_invalid_jwt_token",
            }
            websocket.send_text(json.dumps(auth_msg))

            resp = json.loads(websocket.receive_text())
            assert resp["type"] == "error"
            assert "Authentication failed" in resp["detail"]
