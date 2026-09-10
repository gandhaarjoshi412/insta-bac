"""Instagram events API endpoints."""

import logging
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_device, get_current_user
from app.core.database import get_db
from app.models.device import Device
from app.models.event import InstagramEvent
from app.models.user import User
from app.schemas.events import (
    InstagramEventCreate,
    InstagramEventDetail,
    InstagramEventResponse,
)
from app.services.event_service import event_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["Events"])


@router.post("", response_model=InstagramEventResponse, status_code=status.HTTP_201_CREATED)
async def create_instagram_event(
    req: InstagramEventCreate,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_db),
):
    """Receive an Instagram event from an authenticated client (e.g. Android phone).
    
    Evaluates idempotency, records event, and conditionally triggers intervention
    across user's online laptops if the 5-minute cooldown has expired.
    """
    event, triggered, laptops_count, message = await event_service.process_event(
        session=session,
        device=device,
        event_type=req.event_type,
        occurred_at=req.timestamp,
        client_session_id=req.session_id,
        client_event_id=req.client_event_id,
    )

    return InstagramEventResponse(
        success=True,
        event_id=event.id,
        intervention_triggered=triggered,
        eligible_laptops_count=laptops_count,
        message=message,
    )


@router.get("", response_model=List[InstagramEventDetail])
async def list_user_events(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List recent Instagram events belonging strictly to the authenticated user."""
    stmt = (
        select(InstagramEvent)
        .where(InstagramEvent.user_id == current_user.id)
        .order_by(InstagramEvent.occurred_at.desc())
        .limit(limit)
    )
    events = (await session.execute(stmt)).scalars().all()
    return [InstagramEventDetail.model_validate(e) for e in events]
