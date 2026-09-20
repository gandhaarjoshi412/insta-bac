"""Analytics and Telemetry API endpoints."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsResponse, AnalyticsSummary
from app.services.analytics_service import analytics_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    days: int = Query(default=7, ge=1, le=90, description="Number of days of history"),
    logs_limit: int = Query(default=50, ge=1, le=200, description="Max event/intervention log records"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Fetch comprehensive analytics, historical trends, and logs for the authenticated user."""
    return await analytics_service.get_user_analytics(
        session=session,
        user_id=current_user.id,
        days=days,
        logs_limit=logs_limit,
    )


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Fetch high-level today & all-time metrics summary for quick dashboard cards."""
    res = await analytics_service.get_user_analytics(
        session=session,
        user_id=current_user.id,
        days=1,
        logs_limit=1,
    )
    return res.summary
