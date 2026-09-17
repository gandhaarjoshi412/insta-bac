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


@pytest.mark.asyncio
async def test_laptop_generate_and_android_claim_flow(async_client: httpx.AsyncClient):
    """Test new desktop generation flow:
    1. Laptop requests pairing code from server (POST /api/v1/pairing/generate).
    2. Server generates code and laptop device credentials.
    3. Status is checked (is_claimed == False).
    4. Android claims code (POST /api/v1/pairing/claim).
    5. Status is checked (is_claimed == True, claimed_device_name matches).
    6. Both devices share the same user_id.
    """
    # 1. Laptop requests pairing code without any previous authentication
    gen_resp = await async_client.post(
        "/api/v1/pairing/generate",
        json={
            "device_name": "Gandhaar Fedora Laptop",
            "platform": "Linux 6.11",
            "device_type": "LAPTOP",
        },
    )
    assert gen_resp.status_code == 201
    gen_data = gen_resp.json()
    code = gen_data["pairing_code"]
    assert len(code) == 6
    laptop_device_id = gen_data["device_id"]
    laptop_user_id = gen_data["user_id"]
    laptop_token = gen_data["access_token"]
    assert laptop_token

    # 2. Check pairing status before claim
    status_resp = await async_client.get(f"/api/v1/pairing/status/{code}")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_claimed"] is False
    assert status_resp.json()["is_expired"] is False

    # 3. Android claims pairing code
    android_claim = await async_client.post(
        "/api/v1/pairing/claim",
        json={
            "pairing_code": code,
            "device_name": "Pixel 7 Pro",
            "device_type": "ANDROID",
        },
    )
    assert android_claim.status_code == 201
    android_data = android_claim.json()
    assert android_data["device_id"] != laptop_device_id
    assert android_data["user_id"] == laptop_user_id  # Shared user account!
    assert "access_token" in android_data

    # 4. Check pairing status after claim
    status_resp_after = await async_client.get(f"/api/v1/pairing/status/{code}")
    assert status_resp_after.status_code == 200
    assert status_resp_after.json()["is_claimed"] is True
    assert status_resp_after.json()["claimed_device_name"] == "Pixel 7 Pro"

