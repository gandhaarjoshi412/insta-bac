"""Pydantic schemas for user settings and configuration."""

from pydantic import BaseModel, Field


class UserSettingsResponse(BaseModel):
    """User preferences including intervention cooldown duration."""
    cooldown_seconds: int = Field(
        default=300,
        ge=-1,
        le=86400,
        description="Intervention cooldown duration in seconds (-1 = Mute laptop/track only, 0 = no cooldown)",
    )


class UpdateUserSettingsRequest(BaseModel):
    """Request payload to modify user preferences."""
    cooldown_seconds: int = Field(
        ...,
        ge=-1,
        le=86400,
        description="Intervention cooldown duration in seconds (-1 = Mute laptop/track only, 0 = no cooldown)",
    )
