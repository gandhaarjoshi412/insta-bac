"""End-to-end integration test verifying the complete NoInsta ecosystem:
User registration -> Device pairing -> Laptop WebSocket connection ->
Heartbeat -> Android Instagram Open -> Intervention delivery to Laptop ->
Laptop intervention closure acknowledgement -> Cooldown suppression.
"""

import asyncio
import json
import uuid
import pytest
from starlette.testclient import TestClient

from app.core.database import Base, async_session_factory, engine
from app.main import app as fastapi_app
from app.models.device import DeviceType


def test_full_e2e_intervention_pipeline():
    """Verify end-to-end flow from Android trigger to Laptop intervention and acknowledgment."""

    async def init_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_tables())

    with TestClient(fastapi_app) as client:
        # 1. Register a new user
        reg_resp = client.post(
            "/api/v1/auth/register",
            json={"email": "pipeline_user@example.com", "password": "SecurePassword123!"},
        )
        assert reg_resp.status_code == 201

        # 2. Login to obtain access token
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "pipeline_user@example.com", "password": "SecurePassword123!"},
        )
        assert login_resp.status_code == 200
        user_token = login_resp.json()["access_token"]

        # 3. User creates a pairing code for laptop
        code_resp = client.post(
            "/api/v1/pairing/create",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert code_resp.status_code == 201
        pairing_code = code_resp.json()["pairing_code"]

        # 4. Laptop claims the pairing code
        laptop_claim = client.post(
            "/api/v1/devices/pair",
            json={
                "pairing_code": pairing_code,
                "device_name": "Gandhaar ThinkPad",
                "platform": "linux",
            },
        )
        assert laptop_claim.status_code == 201
        laptop_data = laptop_claim.json()
        laptop_id = laptop_data["device_id"]
        laptop_token = laptop_data["access_token"]

        # 5. User creates another pairing code for phone
        phone_code_resp = client.post(
            "/api/v1/pairing/create",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert phone_code_resp.status_code == 201
        phone_pairing_code = phone_code_resp.json()["pairing_code"]

        # 6. Phone claims pairing code
        phone_claim = client.post(
            "/api/v1/pairing/claim",
            json={
                "pairing_code": phone_pairing_code,
                "device_name": "Pixel 8 Pro",
                "device_type": "ANDROID",
            },
        )
        assert phone_claim.status_code == 201
        phone_token = phone_claim.json()["access_token"]

        # 7. Laptop connects to WebSocket endpoint
        with client.websocket_connect(f"/ws/device/{laptop_id}") as websocket:
            # 8. Authenticate WebSocket
            websocket.send_text(
                json.dumps({
                    "type": "authenticate",
                    "access_token": laptop_token,
                    "device_id": laptop_id,
                })
            )
            auth_ack = json.loads(websocket.receive_text())
            assert auth_ack["type"] == "authenticated"

            # 9. Send heartbeat and verify heartbeat_ack
            websocket.send_text(
                json.dumps({
                    "type": "heartbeat",
                    "device_id": laptop_id,
                })
            )
            hb_ack = json.loads(websocket.receive_text())
            assert hb_ack["type"] == "heartbeat_ack"

            # 10. Phone posts Instagram Open event
            event_resp = client.post(
                "/api/v1/events",
                headers={"Authorization": f"Bearer {phone_token}"},
                json={
                    "event_type": "instagram_open",
                    "session_id": "phone_session_101",
                    "client_event_id": "evt_open_001",
                },
            )
            assert event_resp.status_code == 201
            event_data = event_resp.json()
            assert event_data["success"] is True
            assert event_data["intervention_triggered"] is True
            assert event_data["eligible_laptops_count"] == 1
            event_id = event_data["event_id"]

            # 11. Laptop receives intervention push over WebSocket
            intervention_msg = json.loads(websocket.receive_text())
            assert intervention_msg["type"] == "instagram_open"
            assert intervention_msg["event_id"] == event_id

            # 12. Laptop sends intervention_closed acknowledgment
            websocket.send_text(
                json.dumps({
                    "type": "intervention_closed",
                    "event_id": event_id,
                    "device_id": laptop_id,
                })
            )

            # 13. Phone sends immediate second Instagram Open event -> triggers cooldown
            cooldown_resp = client.post(
                "/api/v1/events",
                headers={"Authorization": f"Bearer {phone_token}"},
                json={
                    "event_type": "instagram_open",
                    "session_id": "phone_session_101",
                    "client_event_id": "evt_open_002",
                },
            )
            assert cooldown_resp.status_code == 201
            cd_data = cooldown_resp.json()
            assert cd_data["intervention_triggered"] is False
            assert "cooldown" in cd_data["message"].lower()

            # 14. Phone sends Instagram Close event
            close_resp = client.post(
                "/api/v1/events",
                headers={"Authorization": f"Bearer {phone_token}"},
                json={
                    "event_type": "instagram_close",
                    "session_id": "phone_session_101",
                    "client_event_id": "evt_close_003",
                },
            )
            assert close_resp.status_code == 201
            assert close_resp.json()["intervention_triggered"] is False
