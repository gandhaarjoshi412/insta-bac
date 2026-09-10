"""Pydantic schemas for device representations and actions."""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    device_type: str
    name: str
    created_at: datetime
    last_seen_at: datetime
    is_online: bool = False
    revoked_at: Optional[datetime] = None


class DeviceRevokeResponse(BaseModel):
    success: bool
    message: str
