"""Pairing API endpoints for code generation and claiming."""

import logging
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import rate_limiter
from app.models.user import User
from app.schemas.pairing import (
    PairingClaimRequest,
    PairingClaimResponse,
    PairingCreateResponse,
)
from app.services.pairing_service import pairing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pairing", tags=["Pairing"])


@router.post("/create", response_model=PairingCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_pairing_code(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Generate a single-use, 6-character pairing code associated with the authenticated user."""
    rate_limiter.check(request)
    code, expires_at, expires_in = await pairing_service.create_pairing_code(
        session=session,
        user_id=current_user.id,
    )
    return PairingCreateResponse(
        pairing_code=code,
        expires_at=expires_at,
        expires_in_seconds=expires_in,
    )


@router.post("/claim", response_model=PairingClaimResponse, status_code=status.HTTP_201_CREATED)
async def claim_pairing_code(
    req: PairingClaimRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Submit a pairing code to create and bind a device (laptop or phone) to the user's account."""
    rate_limiter.check(request)
    device, access_token, refresh_token = await pairing_service.claim_pairing_code(
        session=session,
        raw_code=req.pairing_code,
        device_name=req.device_name,
        device_type=req.device_type,
        platform=req.platform,
    )
    return PairingClaimResponse(
        device_id=device.id,
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=device.user_id,
        message="Device paired successfully.",
    )
