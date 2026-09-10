"""SQLAlchemy database model for User entity."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.refresh_token import RefreshToken
    from app.models.pairing import PairingCode
    from app.models.event import InstagramEvent
    from app.models.session import InstagramSession
    from app.models.intervention import Intervention


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    last_intervention_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # Relationships
    devices: Mapped[List["Device"]] = relationship(
        "Device",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    pairing_codes: Mapped[List["PairingCode"]] = relationship(
        "PairingCode",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    events: Mapped[List["InstagramEvent"]] = relationship(
        "InstagramEvent",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[List["InstagramSession"]] = relationship(
        "InstagramSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    interventions: Mapped[List["Intervention"]] = relationship(
        "Intervention",
        back_populates="user",
        cascade="all, delete-orphan",
    )
