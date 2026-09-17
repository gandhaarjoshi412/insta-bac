"""Pydantic schemas for device pairing flows."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class PairingCreateResponse(BaseModel):
    pairing_code: str
    expires_at: datetime
    expires_in_seconds: int


class PairingClaimRequest(BaseModel):
    pairing_code: str = Field(min_length=4, max_length=32)
    device_name: str = Field(min_length=1, max_length=255)
    device_type: Optional[str] = Field(default="LAPTOP")
    platform: Optional[str] = None


class PairingClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    device_id: uuid.UUID
    access_token: str
    refresh_token: str
    user_id: uuid.UUID
    message: str = "Device paired successfully."


class PairingGenerateRequest(BaseModel):
    device_name: Optional[str] = Field(default=None, max_length=255)
    platform: Optional[str] = None
    device_type: Optional[str] = Field(default="LAPTOP")


class PairingGenerateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pairing_code: str
    expires_at: datetime
    expires_in_seconds: int
    device_id: uuid.UUID
    access_token: str
    refresh_token: str
    user_id: uuid.UUID
    message: str = "Pairing code generated successfully."


class PairingStatusResponse(BaseModel):
    pairing_code: str
    is_claimed: bool
    claimed_device_name: Optional[str] = None
    expires_at: datetime
    is_expired: bool
    message: str = "Status retrieved successfully."

