"""SQLAlchemy database model for InstagramEvent entity."""

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.device import Device
    from app.models.session import InstagramSession
    from app.models.intervention import Intervention


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    INSTAGRAM_OPEN = "instagram_open"
    INSTAGRAM_CLOSE = "instagram_close"


class InstagramEvent(Base):
    __tablename__ = "instagram_events"

    __table_args__ = (
        UniqueConstraint("device_id", "client_event_id", name="uq_device_client_event_id"),
    )

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
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("devices.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    client_event_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("instagram_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="events")
    device: Mapped["Device"] = relationship("Device", back_populates="events")
    session: Mapped[Optional["InstagramSession"]] = relationship("InstagramSession", back_populates="events")
    interventions: Mapped[List["Intervention"]] = relationship(
        "Intervention",
        back_populates="event",
        cascade="all, delete-orphan",
    )
