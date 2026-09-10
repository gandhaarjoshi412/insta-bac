"""Unit and integration tests for 5-minute global intervention cooldown."""

from datetime import datetime, timedelta, timezone
import pytest
import httpx


@pytest.mark.asyncio
async def test_five_minute_cooldown_logic(async_client: httpx.AsyncClient):
    # 1. Register and Login User
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "cooldown_user@example.com", "password": "Password123!"},
    )
    u_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "cooldown_user@example.com", "password": "Password123!"},
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
        json={"pairing_code": code, "device_name": "Galaxy S24", "device_type": "ANDROID"},
    )
    phone_token = phone_resp.json()["access_token"]

    # Base timestamp
    t0 = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    # 3. First Instagram Open event at 12:00
    r1 = await async_client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {phone_token}"},
        json={
            "event_type": "instagram_open",
            "timestamp": t0.isoformat(),
            "client_event_id": "evt_t0",
        },
    )
    assert r1.status_code == 201
    # Cooldown was not active (though no laptop online yet)
    assert "cooldown" not in r1.json()["message"].lower()

    # 4. Second Instagram Open at 12:02 (2 minutes later, within 5 min cooldown)
    t1 = t0 + timedelta(minutes=2)
    r2 = await async_client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {phone_token}"},
        json={
            "event_type": "instagram_open",
            "timestamp": t1.isoformat(),
            "client_event_id": "evt_t1",
        },
    )
    assert r2.status_code == 201
    d2 = r2.json()
    assert d2["intervention_triggered"] is False
    assert "cooldown" in d2["message"].lower()

    # 5. Third Instagram Open at 12:06 (6 minutes later, cooldown has expired)
    t2 = t0 + timedelta(minutes=6)
    r3 = await async_client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {phone_token}"},
        json={
            "event_type": "instagram_open",
            "timestamp": t2.isoformat(),
            "client_event_id": "evt_t2",
        },
    )
    assert r3.status_code == 201
    d3 = r3.json()
    assert "cooldown" not in d3["message"].lower()
