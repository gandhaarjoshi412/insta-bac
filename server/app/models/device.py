"""SQLAlchemy database model for Device entity (Android and Laptop)."""

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.refresh_token import RefreshToken
    from app.models.event import InstagramEvent
    from app.models.intervention import Intervention


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeviceType(str, Enum):
    ANDROID = "ANDROID"
    LAPTOP = "LAPTOP"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    device_type: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    credential_hash: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
        nullable=False,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="devices")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="device",
        cascade="all, delete-orphan",
    )
    events: Mapped[List["InstagramEvent"]] = relationship(
        "InstagramEvent",
        back_populates="device",
        cascade="all, delete-orphan",
    )
    interventions: Mapped[List["Intervention"]] = relationship(
        "Intervention",
        back_populates="laptop_device",
        cascade="all, delete-orphan",
    )

    @property
    def is_active(self) -> bool:
        """Check if device is active and not revoked."""
        return self.revoked_at is None
