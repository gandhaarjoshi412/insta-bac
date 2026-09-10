"""Unit and integration tests for authentication endpoints."""

import pytest
import httpx


@pytest.mark.asyncio
async def test_register_and_login_flow(async_client: httpx.AsyncClient):
    # 1. Register
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "testuser@example.com", "password": "SecurePassword123!"},
    )
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    assert reg_data["email"] == "testuser@example.com"
    assert "id" in reg_data

    # 2. Duplicate registration should return 409
    dup_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "testuser@example.com", "password": "SecurePassword123!"},
    )
    assert dup_resp.status_code == 409

    # 3. Login with correct credentials
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"

    # 4. Login with wrong password
    bad_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401

    # 5. Access protected /me endpoint
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "testuser@example.com"


@pytest.mark.asyncio
async def test_unauthorized_access(async_client: httpx.AsyncClient):
    # Missing token
    resp = await async_client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)

    # Invalid token
    resp2 = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert resp2.status_code == 401
