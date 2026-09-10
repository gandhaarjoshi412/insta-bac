"""Unit and integration tests for pairing code creation, claiming, and reuse prevention."""

import pytest
import httpx


@pytest.mark.asyncio
async def test_pairing_flow(async_client: httpx.AsyncClient):
    # 1. Register and Login User
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "pair_user@example.com", "password": "Password123!"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "pair_user@example.com", "password": "Password123!"},
    )
    user_token = login_resp.json()["access_token"]

    # 2. Create Pairing Code
    pair_resp = await async_client.post(
        "/api/v1/pairing/create",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert pair_resp.status_code == 201
    pair_data = pair_resp.json()
    code = pair_data["pairing_code"]
    assert len(code) == 6
    assert code.isalnum()

    # 3. Laptop Claims Pairing Code
    claim_resp = await async_client.post(
        "/api/v1/pairing/claim",
        json={
            "pairing_code": code,
            "device_name": "Gandhaar Fedora Laptop",
            "device_type": "LAPTOP",
        },
    )
    assert claim_resp.status_code == 201
    claim_data = claim_resp.json()
    assert "device_id" in claim_data
    assert "access_token" in claim_data
    assert "refresh_token" in claim_data
    assert claim_data["message"] == "Device paired successfully."

    # 4. Attempting to reuse same pairing code must fail
    reuse_resp = await async_client.post(
        "/api/v1/pairing/claim",
        json={
            "pairing_code": code,
            "device_name": "Second Attempt",
            "device_type": "LAPTOP",
        },
    )
    assert reuse_resp.status_code == 400

    # 5. Invalid pairing code
    invalid_resp = await async_client.post(
        "/api/v1/pairing/claim",
        json={
            "pairing_code": "NONEXIST",
            "device_name": "Fake Laptop",
            "device_type": "LAPTOP",
        },
    )
    assert invalid_resp.status_code == 400

    # 6. Test token refresh using device refresh token
    refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": claim_data["refresh_token"],
            "device_id": claim_data["device_id"],
        },
    )
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()


@pytest.mark.asyncio
async def test_pairing_devices_pair_alias(async_client: httpx.AsyncClient):
    """Verify /api/v1/devices/pair works as an alias for client compatibility."""
    # Register & Login
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "alias_user@example.com", "password": "Password123!"},
    )
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "alias_user@example.com", "password": "Password123!"},
    )
    user_token = login_resp.json()["access_token"]

    # Create Code
    pair_resp = await async_client.post(
        "/api/v1/pairing/create",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    code = pair_resp.json()["pairing_code"]

    # Claim via alias
    claim_resp = await async_client.post(
        "/api/v1/devices/pair",
        json={
            "pairing_code": code,
            "device_name": "Alias Laptop",
            "device_type": "LAPTOP",
        },
    )
    assert claim_resp.status_code == 201
    assert "device_id" in claim_resp.json()
