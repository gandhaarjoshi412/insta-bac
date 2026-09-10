"""Pytest fixtures for server testing using in-memory async SQLite."""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

# Insert server directory into sys.path
SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

# Environment variables for testing
os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = "test_jwt_secret_key_testing_min_32_bytes"
os.environ["INSTAGRAM_COOLDOWN_SECONDS"] = "300"
os.environ["PAIRING_CODE_EXPIRE_MINUTES"] = "10"
os.environ["LAPTOP_HEARTBEAT_SECONDS"] = "120"
os.environ["LAPTOP_OFFLINE_SECONDS"] = "900"

import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # Register all models with Base.metadata
from app.core.config import settings
settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"

from app.core.database import Base, async_session_factory, engine, get_db
from app.main import app as fastapi_app


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create all database tables on the engine before test, clean up after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional AsyncSession."""
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def async_client(test_engine, db_session) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an AsyncClient wired to the test database."""
    async def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    fastapi_app.dependency_overrides.clear()
