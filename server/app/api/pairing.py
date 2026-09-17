"""Pairing API endpoints for code generation and claiming."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_current_user
from app.core.database import get_db
from app.core.rate_limit import rate_limiter
from app.models.user import User
from app.schemas.pairing import (
    PairingClaimRequest,
    PairingClaimResponse,
    PairingCreateResponse,
    PairingGenerateRequest,
    PairingGenerateResponse,
    PairingStatusResponse,
)
from app.services.pairing_service import pairing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pairing", tags=["Pairing"])


@router.post("/generate", response_model=PairingGenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_pairing_code_desktop(
    req: PairingGenerateRequest,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Generate a single-use 6-character pairing code for a laptop client.
    
    Registers the laptop as a device, creates a user session if not already logged in,
    issues credentials for the laptop, and returns the pairing code to enter on the Android phone.
    """
    rate_limiter.check(request)
    user_id = current_user.id if current_user else None
    code, expires_at, expires_in, device, access_token, refresh_token = (
        await pairing_service.generate_laptop_pairing(
            session=session,
            device_name=req.device_name,
            platform=req.platform,
            user_id=user_id,
        )
    )
    return PairingGenerateResponse(
        pairing_code=code,
        expires_at=expires_at,
        expires_in_seconds=expires_in,
        device_id=device.id,
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=device.user_id,
        message="Pairing code generated successfully.",
    )


@router.get("/status/{pairing_code}", response_model=PairingStatusResponse)
async def check_pairing_code_status(
    pairing_code: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Check whether a pairing code has been claimed by the phone."""
    rate_limiter.check(request)
    exists, is_claimed, claimed_device_name, expires_at, is_expired = (
        await pairing_service.get_pairing_status(
            session=session,
            raw_code=pairing_code,
        )
    )
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or non-existent pairing code.",
        )

    return PairingStatusResponse(
        pairing_code=pairing_code.strip().upper(),
        is_claimed=is_claimed,
        claimed_device_name=claimed_device_name,
        expires_at=expires_at,
        is_expired=is_expired,
        message="Code claimed." if is_claimed else "Code pending claim.",
    )



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
