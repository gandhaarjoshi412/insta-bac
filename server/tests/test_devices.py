"""Unit and integration tests for device management, ownership, and revocation."""

import pytest
import httpx


@pytest.mark.asyncio
async def test_device_ownership_and_revocation(async_client: httpx.AsyncClient):
    # Register User 1
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "u1@example.com", "password": "Password123!"},
    )
    u1_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "u1@example.com", "password": "Password123!"},
    )
    u1_token = u1_login.json()["access_token"]

    # Register User 2
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "u2@example.com", "password": "Password123!"},
    )
    u2_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "u2@example.com", "password": "Password123!"},
    )
    u2_token = u2_login.json()["access_token"]

    # User 1 pairs two laptops
    for name in ["Laptop-1", "Laptop-2"]:
        p_resp = await async_client.post(
            "/api/v1/pairing/create",
            headers={"Authorization": f"Bearer {u1_token}"},
        )
        code = p_resp.json()["pairing_code"]
        await async_client.post(
            "/api/v1/pairing/claim",
            json={"pairing_code": code, "device_name": name, "device_type": "LAPTOP"},
        )

    # User 1 lists devices (should have 2)
    dev_resp = await async_client.get(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {u1_token}"},
    )
    assert dev_resp.status_code == 200
    devices = dev_resp.json()
    assert len(devices) == 2
    laptop_1_id = devices[0]["id"]

    # User 2 lists devices (should have 0)
    u2_devs = await async_client.get(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {u2_token}"},
    )
    assert len(u2_devs.json()) == 0

    # User 2 attempts to revoke User 1's device -> 404 (ownership check)
    bad_revoke = await async_client.delete(
        f"/api/v1/devices/{laptop_1_id}",
        headers={"Authorization": f"Bearer {u2_token}"},
    )
    assert bad_revoke.status_code == 404

    # User 1 revokes Laptop 1 -> 200
    revoke_resp = await async_client.delete(
        f"/api/v1/devices/{laptop_1_id}",
        headers={"Authorization": f"Bearer {u1_token}"},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["success"] is True

    # Check device details now show revoked
    chk_resp = await async_client.get(
        f"/api/v1/devices/{laptop_1_id}",
        headers={"Authorization": f"Bearer {u1_token}"},
    )
    assert chk_resp.status_code == 200
    assert chk_resp.json()["revoked_at"] is not None
