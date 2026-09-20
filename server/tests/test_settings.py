"""Tests for user settings API and customizable cooldown configuration."""

import pytest
import httpx
from starlette.testclient import TestClient


@pytest.mark.anyio
async def test_user_settings_get_and_update(async_client: httpx.AsyncClient):
    # 1. Register a test user
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "cooldown_custom@example.com", "password": "Password123!"},
    )
    assert reg_resp.status_code == 201

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "cooldown_custom@example.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get default settings
    get_resp = await async_client.get("/api/v1/settings", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["cooldown_seconds"] == 300

    # 3. Update cooldown to 60 seconds (1 minute)
    patch_resp = await async_client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"cooldown_seconds": 60},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["cooldown_seconds"] == 60

    # 4. Verify updated setting persists
    get_resp2 = await async_client.get("/api/v1/settings", headers=headers)
    assert get_resp2.status_code == 200
    assert get_resp2.json()["cooldown_seconds"] == 60

    # 5. Disable cooldown (0 seconds)
    put_resp = await async_client.put(
        "/api/v1/settings",
        headers=headers,
        json={"cooldown_seconds": 0},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["cooldown_seconds"] == 0
