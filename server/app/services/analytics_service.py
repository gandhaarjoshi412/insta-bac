"""Service computing productivity analytics, usage sessions, and intervention telemetry."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, List, Optional
import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.event import EventType, InstagramEvent
from app.models.intervention import Intervention
from app.models.session import InstagramSession
from app.schemas.analytics import (
    AnalyticsResponse,
    AnalyticsSummary,
    DailyBreakdown,
    EventLogItem,
    InterventionLogItem,
)

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalyticsService:
    """Aggregates telemetry and provides structured analytics."""

    @staticmethod
    async def get_user_analytics(
        session: AsyncSession,
        user_id: uuid.UUID,
        days: int = 7,
        logs_limit: int = 50,
    ) -> AnalyticsResponse:
        now = utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        since_date = today_start - timedelta(days=max(0, days - 1))

        # 1. Fetch user devices map for fast name lookup
        devices_stmt = select(Device).where(Device.user_id == user_id)
        devices_res = (await session.execute(devices_stmt)).scalars().all()
        device_map: Dict[uuid.UUID, Device] = {d.id: d for d in devices_res}

        # 2. Summary stats
        # Total opens today
        opens_today_stmt = (
            select(func.count(InstagramEvent.id))
            .where(InstagramEvent.user_id == user_id)
            .where(InstagramEvent.event_type == EventType.INSTAGRAM_OPEN.value)
            .where(InstagramEvent.occurred_at >= today_start)
        )
        opens_today = (await session.execute(opens_today_stmt)).scalar() or 0

        # Total opens all time
        opens_all_stmt = (
            select(func.count(InstagramEvent.id))
            .where(InstagramEvent.user_id == user_id)
            .where(InstagramEvent.event_type == EventType.INSTAGRAM_OPEN.value)
        )
        opens_all_time = (await session.execute(opens_all_stmt)).scalar() or 0

        # Total sessions all time
        sessions_all_stmt = (
            select(func.count(InstagramSession.id))
            .where(InstagramSession.user_id == user_id)
        )
        sessions_all_time = (await session.execute(sessions_all_stmt)).scalar() or 0

        # Interventions today & all time
        interv_today_stmt = (
            select(func.count(Intervention.id))
            .where(Intervention.user_id == user_id)
            .where(Intervention.sent_at >= today_start)
        )
        interventions_today = (await session.execute(interv_today_stmt)).scalar() or 0

        interv_all_stmt = (
            select(func.count(Intervention.id))
            .where(Intervention.user_id == user_id)
        )
        interventions_all_time = (await session.execute(interv_all_stmt)).scalar() or 0

        # Latest open timestamp
        latest_open_stmt = (
            select(InstagramEvent.occurred_at)
            .where(InstagramEvent.user_id == user_id)
            .where(InstagramEvent.event_type == EventType.INSTAGRAM_OPEN.value)
            .order_by(desc(InstagramEvent.occurred_at))
            .limit(1)
        )
        last_opened_at = (await session.execute(latest_open_stmt)).scalar_one_or_none()

        # 3. Time spent today & Daily Breakdown for last `days`
        sessions_window_stmt = (
            select(InstagramSession)
            .where(InstagramSession.user_id == user_id)
            .where(InstagramSession.started_at >= since_date)
        )
        sessions_window = (await session.execute(sessions_window_stmt)).scalars().all()

        daily_time: Dict[str, int] = defaultdict(int)
        time_today_seconds = 0

        for sess in sessions_window:
            start_ts = sess.started_at
            if start_ts.tzinfo is None:
                start_ts = start_ts.replace(tzinfo=timezone.utc)

            end_ts = sess.ended_at
            if end_ts is not None:
                if end_ts.tzinfo is None:
                    end_ts = end_ts.replace(tzinfo=timezone.utc)
                dur = max(0, int((end_ts - start_ts).total_seconds()))
            else:
                # Active or unclosed session: estimate capped at 5 minutes
                dur = min(300, max(0, int((now - start_ts).total_seconds())))

            date_str = start_ts.strftime("%Y-%m-%d")
            daily_time[date_str] += dur
            if start_ts >= today_start:
                time_today_seconds += dur

        # 4. Daily opens and interventions in the breakdown window
        events_window_stmt = (
            select(InstagramEvent.occurred_at)
            .where(InstagramEvent.user_id == user_id)
            .where(InstagramEvent.event_type == EventType.INSTAGRAM_OPEN.value)
            .where(InstagramEvent.occurred_at >= since_date)
        )
        events_window = (await session.execute(events_window_stmt)).scalars().all()
        daily_opens: Dict[str, int] = defaultdict(int)
        for ev_time in events_window:
            if ev_time.tzinfo is None:
                ev_time = ev_time.replace(tzinfo=timezone.utc)
            daily_opens[ev_time.strftime("%Y-%m-%d")] += 1

        interv_window_stmt = (
            select(Intervention.sent_at)
            .where(Intervention.user_id == user_id)
            .where(Intervention.sent_at >= since_date)
        )
        interv_window = (await session.execute(interv_window_stmt)).scalars().all()
        daily_interv: Dict[str, int] = defaultdict(int)
        for i_time in interv_window:
            if i_time.tzinfo is None:
                i_time = i_time.replace(tzinfo=timezone.utc)
            daily_interv[i_time.strftime("%Y-%m-%d")] += 1

        # Build consecutive daily list (oldest to newest)
        daily_breakdown: List[DailyBreakdown] = []
        for d_offset in range(days - 1, -1, -1):
            d_date = (now - timedelta(days=d_offset)).strftime("%Y-%m-%d")
            daily_breakdown.append(
                DailyBreakdown(
                    date=d_date,
                    opens=daily_opens[d_date],
                    time_spent_seconds=daily_time[d_date],
                    interventions=daily_interv[d_date],
                )
            )

        # 5. Recent events list
        recent_events_stmt = (
            select(InstagramEvent)
            .where(InstagramEvent.user_id == user_id)
            .order_by(desc(InstagramEvent.occurred_at))
            .limit(logs_limit)
        )
        recent_events_res = (await session.execute(recent_events_stmt)).scalars().all()
        recent_events: List[EventLogItem] = []
        for e in recent_events_res:
            dev = device_map.get(e.device_id)
            recent_events.append(
                EventLogItem(
                    id=e.id,
                    event_type=e.event_type,
                    occurred_at=e.occurred_at,
                    device_id=e.device_id,
                    device_name=dev.name if dev else "Unknown Device",
                    device_type=dev.device_type if dev else "ANDROID",
                    session_id=e.session_id,
                    client_event_id=e.client_event_id,
                )
            )

        # 6. Recent interventions list
        recent_interv_stmt = (
            select(Intervention)
            .where(Intervention.user_id == user_id)
            .order_by(desc(Intervention.sent_at))
            .limit(logs_limit)
        )
        recent_interv_res = (await session.execute(recent_interv_stmt)).scalars().all()
        recent_interventions: List[InterventionLogItem] = []
        for i in recent_interv_res:
            laptop_dev = device_map.get(i.laptop_device_id)
            dur_ack: Optional[float] = None
            if i.acknowledged_at and i.sent_at:
                s_at = i.sent_at.replace(tzinfo=timezone.utc) if i.sent_at.tzinfo is None else i.sent_at
                a_at = (
                    i.acknowledged_at.replace(tzinfo=timezone.utc)
                    if i.acknowledged_at.tzinfo is None
                    else i.acknowledged_at
                )
                dur_ack = round((a_at - s_at).total_seconds(), 2)

            recent_interventions.append(
                InterventionLogItem(
                    id=i.id,
                    event_id=i.event_id,
                    sent_at=i.sent_at,
                    acknowledged_at=i.acknowledged_at,
                    status=i.status,
                    laptop_device_id=i.laptop_device_id,
                    laptop_device_name=laptop_dev.name if laptop_dev else "Laptop",
                    duration_to_ack_seconds=dur_ack,
                )
            )

        summary = AnalyticsSummary(
            total_opens_today=opens_today,
            total_time_today_seconds=time_today_seconds,
            total_interventions_today=interventions_today,
            total_opens_all_time=opens_all_time,
            total_sessions_all_time=sessions_all_time,
            total_interventions_all_time=interventions_all_time,
            last_opened_at=last_opened_at,
        )

        return AnalyticsResponse(
            summary=summary,
            daily_breakdown=daily_breakdown,
            recent_events=recent_events,
            recent_interventions=recent_interventions,
        )


analytics_service = AnalyticsService()
