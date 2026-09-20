"""Pydantic schemas for user settings and configuration."""

from pydantic import BaseModel, Field


class UserSettingsResponse(BaseModel):
    """User preferences including intervention cooldown duration."""
    cooldown_seconds: int = Field(
        default=300,
        ge=0,
        le=86400,
        description="Intervention cooldown duration in seconds (0 = disabled)",
    )


class UpdateUserSettingsRequest(BaseModel):
    """Request payload to modify user preferences."""
    cooldown_seconds: int = Field(
        ...,
        ge=0,
        le=86400,
        description="Intervention cooldown duration in seconds (0 = disabled)",
    )
