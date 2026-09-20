"""Pydantic schemas for analytics and event logs."""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsSummary(BaseModel):
    """Key productivity and intervention metrics."""
    total_opens_today: int = Field(default=0, description="Total Instagram opens today")
    total_time_today_seconds: int = Field(default=0, description="Total seconds spent on Instagram today")
    total_interventions_today: int = Field(default=0, description="Total interventions triggered today")
    total_opens_all_time: int = Field(default=0, description="All-time Instagram opens")
    total_sessions_all_time: int = Field(default=0, description="All-time Instagram sessions")
    total_interventions_all_time: int = Field(default=0, description="All-time interventions triggered")
    last_opened_at: Optional[datetime] = Field(default=None, description="Timestamp of latest Instagram open")


class DailyBreakdown(BaseModel):
    """Daily aggregated metrics for trends."""
    date: str  # YYYY-MM-DD
    opens: int = 0
    time_spent_seconds: int = 0
    interventions: int = 0


class EventLogItem(BaseModel):
    """Detailed event log record."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    occurred_at: datetime
    device_id: uuid.UUID
    device_name: str = "Unknown Device"
    device_type: str = "ANDROID"
    session_id: Optional[uuid.UUID] = None
    client_event_id: Optional[str] = None


class InterventionLogItem(BaseModel):
    """Detailed intervention log record."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    sent_at: datetime
    acknowledged_at: Optional[datetime] = None
    status: str
    laptop_device_id: uuid.UUID
    laptop_device_name: str = "Unknown Laptop"
    duration_to_ack_seconds: Optional[float] = None


class AnalyticsResponse(BaseModel):
    """Consolidated analytics report and historical logs."""
    summary: AnalyticsSummary
    daily_breakdown: List[DailyBreakdown] = Field(default_factory=list)
    recent_events: List[EventLogItem] = Field(default_factory=list)
    recent_interventions: List[InterventionLogItem] = Field(default_factory=list)
