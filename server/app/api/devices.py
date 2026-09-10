"""Device management API endpoints."""

from datetime import datetime, timezone
import logging
from typing import List
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import rate_limiter
from app.models.device import Device
from app.models.user import User
from app.schemas.devices import DeviceResponse, DeviceRevokeResponse
from app.schemas.pairing import PairingClaimRequest, PairingClaimResponse
from app.services.pairing_service import pairing_service
from app.services.presence_service import presence_service
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/devices", tags=["Devices"])


@router.post("/pair", response_model=PairingClaimResponse, status_code=status.HTTP_201_CREATED)
async def pair_device_alias(
    req: PairingClaimRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Pair a device via pairing code (alias to /api/v1/pairing/claim)."""
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


@router.get("", response_model=List[DeviceResponse])
async def list_devices(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List all registered devices belonging to the authenticated user."""
    stmt = (
        select(Device)
        .where(Device.user_id == current_user.id)
        .order_by(Device.created_at.desc())
    )
    devices = (await session.execute(stmt)).scalars().all()

    response = []
    for d in devices:
        is_online = presence_service.is_laptop_online(d) if d.device_type == "LAPTOP" else False
        res = DeviceResponse.model_validate(d)
        res.is_online = is_online
        response.append(res)

    return response


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve details of a specific device belonging to the user."""
    stmt = (
        select(Device)
        .where(Device.id == device_id)
        .where(Device.user_id == current_user.id)
    )
    device = (await session.execute(stmt)).scalar_one_or_none()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found.",
        )

    is_online = presence_service.is_laptop_online(device) if device.device_type == "LAPTOP" else False
    res = DeviceResponse.model_validate(device)
    res.is_online = is_online
    return res


@router.delete("/{device_id}", response_model=DeviceRevokeResponse)
async def revoke_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Revoke a device. Invalidates future authentication and terminates active WebSocket."""
    stmt = (
        select(Device)
        .where(Device.id == device_id)
        .where(Device.user_id == current_user.id)
    )
    device = (await session.execute(stmt)).scalar_one_or_none()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found.",
        )

    now = datetime.now(timezone.utc)
    device.revoked_at = now
    await session.commit()

    # Disconnect active WebSocket if connected
    await ws_manager.disconnect(device.id, current_user.id)
    logger.info("Device %s revoked by user %s", device_id, current_user.id)

    return DeviceRevokeResponse(
        success=True,
        message="Device revoked successfully.",
    )
