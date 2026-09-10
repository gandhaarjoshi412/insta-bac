"""Unit and integration tests for Instagram events, session tracking, and idempotency."""

import pytest
import httpx


@pytest.mark.asyncio
async def test_events_flow_and_idempotency(async_client: httpx.AsyncClient):
    # 1. Register and Login User
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "event_user@example.com", "password": "Password123!"},
    )
    u_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "event_user@example.com", "password": "Password123!"},
    )
    user_token = u_login.json()["access_token"]

    # 2. Pair Android Device
    p_resp = await async_client.post(
        "/api/v1/pairing/create",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    code = p_resp.json()["pairing_code"]
    phone_resp = await async_client.post(
        "/api/v1/pairing/claim",
        json={"pairing_code": code, "device_name": "Pixel 8", "device_type": "ANDROID"},
    )
    phone_token = phone_resp.json()["access_token"]

    # 3. Android sends Instagram Open event with client_event_id and session_id
    open_resp = await async_client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {phone_token}"},
        json={
            "event_type": "instagram_open",
            "session_id": "session_abc123",
            "client_event_id": "client_evt_001",
        },
    )
    assert open_resp.status_code == 201
    open_data = open_resp.json()
    assert open_data["success"] is True
    event_id = open_data["event_id"]

    # 4. Idempotency test: Resend same client_event_id
    replay_resp = await async_client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {phone_token}"},
        json={
            "event_type": "instagram_open",
            "session_id": "session_abc123",
            "client_event_id": "client_evt_001",
        },
    )
    assert replay_resp.status_code == 201
    replay_data = replay_resp.json()
    assert replay_data["event_id"] == event_id
    assert "Duplicate" in replay_data["message"]

    # 5. Android sends Instagram Close event
    close_resp = await async_client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {phone_token}"},
        json={
            "event_type": "instagram_close",
            "session_id": "session_abc123",
            "client_event_id": "client_evt_002",
        },
    )
    assert close_resp.status_code == 201
    assert close_resp.json()["intervention_triggered"] is False

    # 6. User views event history
    list_resp = await async_client.get(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert list_resp.status_code == 200
    events = list_resp.json()
    assert len(events) == 2
    types = [e["event_type"] for e in events]
    assert "instagram_open" in types
    assert "instagram_close" in types
