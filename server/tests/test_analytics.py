"""Unit and integration tests for Analytics API endpoints."""

import pytest
import httpx


@pytest.mark.asyncio
async def test_analytics_api_flow(async_client: httpx.AsyncClient):
    # 1. Register and Login User
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "analytics_user@example.com", "password": "Password123!"},
    )
    u_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "analytics_user@example.com", "password": "Password123!"},
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

    # 3. Initially check analytics (should be empty/zero)
    a_resp = await async_client.get(
        "/api/v1/analytics",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert a_resp.status_code == 200
    a_data = a_resp.json()
    assert a_data["summary"]["total_opens_today"] == 0
    assert a_data["summary"]["total_opens_all_time"] == 0
    assert len(a_data["recent_events"]) == 0

    # 4. Trigger Instagram Open and Close events
    await async_client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {phone_token}"},
        json={
            "event_type": "instagram_open",
            "session_id": "session_analytics_1",
            "client_event_id": "evt_an_01",
        },
    )
    await async_client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {phone_token}"},
        json={
            "event_type": "instagram_close",
            "session_id": "session_analytics_1",
            "client_event_id": "evt_an_02",
        },
    )

    # 5. Check analytics again
    a_resp2 = await async_client.get(
        "/api/v1/analytics",
        headers={"Authorization": f"Bearer {phone_token}"},
    )
    assert a_resp2.status_code == 200
    a_data2 = a_resp2.json()
    assert a_data2["summary"]["total_opens_today"] == 1
    assert a_data2["summary"]["total_opens_all_time"] == 1
    assert a_data2["summary"]["total_sessions_all_time"] == 1
    assert len(a_data2["recent_events"]) == 2
    assert a_data2["recent_events"][0]["device_name"] == "Galaxy S24"

    # 6. Check summary endpoint
    s_resp = await async_client.get(
        "/api/v1/analytics/summary",
        headers={"Authorization": f"Bearer {phone_token}"},
    )
    assert s_resp.status_code == 200
    s_data = s_resp.json()
    assert s_data["total_opens_today"] == 1
