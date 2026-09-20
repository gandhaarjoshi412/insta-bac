"""API router for user preferences and configuration settings."""

import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.settings import UpdateUserSettingsRequest, UserSettingsResponse

logger = logging.getLogger(__name__)

settings_router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


@settings_router.get("", response_model=UserSettingsResponse)
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    """Retrieve current settings (cooldown, etc.) for the authenticated user."""
    stmt = select(User).where(User.id == current_user.id)
    user = (await db.execute(stmt)).scalar_one()
    cooldown = user.cooldown_seconds if user.cooldown_seconds is not None else 300
    return UserSettingsResponse(cooldown_seconds=cooldown)


@settings_router.put("", response_model=UserSettingsResponse)
@settings_router.patch("", response_model=UserSettingsResponse)
async def update_user_settings(
    req: UpdateUserSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    """Update settings (e.g. intervention cooldown duration) for the authenticated user."""
    stmt = select(User).where(User.id == current_user.id).with_for_update()
    user = (await db.execute(stmt)).scalar_one()
    user.cooldown_seconds = req.cooldown_seconds
    await db.commit()
    await db.refresh(user)
    logger.info("Updated cooldown_seconds to %d for user %s", user.cooldown_seconds, user.id)
    return UserSettingsResponse(cooldown_seconds=user.cooldown_seconds)
