"""Health check API endpoints."""

import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
@router.get("/api/v1/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Lightweight health status probe."""
    return {"status": "ok", "service": "noinsta-server"}


@router.get("/health/ready", status_code=status.HTTP_200_OK)
@router.get("/api/v1/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check(session: AsyncSession = Depends(get_db)):
    """Readiness probe checking database connectivity."""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        logger.error("Readiness check database failure: %s", exc)
        return {"status": "unhealthy", "database": "disconnected"}
