"""Instagram event processing, session tracking, 5-minute cooldown, and intervention dispatch."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional, Tuple
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.device import Device
from app.models.event import EventType, InstagramEvent
from app.models.intervention import Intervention, InterventionStatus
from app.models.session import InstagramSession
from app.models.user import User
from app.services.presence_service import presence_service
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventService:
    """Coordinates event persistence, cooldown enforcement, and laptop intervention delivery."""

    @staticmethod
    async def process_event(
        session: AsyncSession,
        device: Device,
        event_type: str,
        occurred_at: Optional[datetime] = None,
        client_session_id: Optional[str] = None,
        client_event_id: Optional[str] = None,
    ) -> Tuple[InstagramEvent, bool, int, str]:
        """Process incoming Instagram event from an authenticated Android device.
        
        Returns: (event: InstagramEvent, intervention_triggered: bool, eligible_laptops_count: int, message: str)
        """
        now = utcnow()
        event_time = occurred_at or now
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)

        # 1. Idempotency check: if duplicate client_event_id already processed, return existing
        if client_event_id:
            dup_stmt = (
                select(InstagramEvent)
                .where(InstagramEvent.device_id == device.id)
                .where(InstagramEvent.client_event_id == client_event_id)
            )
            existing_event = (await session.execute(dup_stmt)).scalar_one_or_none()
            if existing_event:
                logger.info("Idempotent replay detected for event %s (device %s)", client_event_id, device.id)
                return existing_event, False, 0, "Duplicate event recognized (idempotency key matched)."

        # 2. Session tracking (if client_session_id provided)
        db_session_id: Optional[uuid.UUID] = None
        if client_session_id:
            sess_stmt = (
                select(InstagramSession)
                .where(InstagramSession.device_id == device.id)
                .where(InstagramSession.client_session_id == client_session_id)
            )
            insta_sess = (await session.execute(sess_stmt)).scalar_one_or_none()

            if not insta_sess:
                insta_sess = InstagramSession(
                    user_id=device.user_id,
                    device_id=device.id,
                    client_session_id=client_session_id,
                    started_at=event_time,
                )
                session.add(insta_sess)
                await session.flush()
            elif event_type.lower() in ("instagram_close", "close"):
                insta_sess.ended_at = event_time

            db_session_id = insta_sess.id

        # 3. Create and persist InstagramEvent record
        normalized_type = event_type.lower()
        if "close" in normalized_type:
            db_event_type = EventType.INSTAGRAM_CLOSE.value
        else:
            db_event_type = EventType.INSTAGRAM_OPEN.value

        event = InstagramEvent(
            user_id=device.user_id,
            device_id=device.id,
            client_event_id=client_event_id,
            event_type=db_event_type,
            session_id=db_session_id,
            occurred_at=event_time,
        )
        session.add(event)

        # 4. Evaluate intervention triggering (Only for instagram_open)
        if db_event_type != EventType.INSTAGRAM_OPEN.value:
            await session.commit()
            await session.refresh(event)
            return event, False, 0, "Instagram close event recorded."

        # 5. Cooldown evaluation with row-level locking on user to prevent race conditions
        user_stmt = select(User).where(User.id == device.user_id).with_for_update()
        user = (await session.execute(user_stmt)).scalar_one()

        cooldown_duration = timedelta(seconds=settings.INSTAGRAM_COOLDOWN_SECONDS)
        is_cooldown_active = False

        if user.last_intervention_at is not None:
            last_interv = user.last_intervention_at
            if last_interv.tzinfo is None:
                last_interv = last_interv.replace(tzinfo=timezone.utc)

            if (event_time - last_interv) < cooldown_duration:
                is_cooldown_active = True
                remaining = int((cooldown_duration - (event_time - last_interv)).total_seconds())
                logger.info("Cooldown active for user %s (%d seconds remaining). Event recorded.", user.id, remaining)

        if is_cooldown_active:
            await session.commit()
            await session.refresh(event)
            return event, False, 0, "Event recorded; intervention suppressed due to 5-minute cooldown."

        # Cooldown expired -> update last_intervention_at and authorize intervention
        user.last_intervention_at = event_time
        await session.commit()
        await session.refresh(event)

        # 6. Find eligible online laptops for user
        online_laptops = await presence_service.get_online_laptops_for_user(session, user.id)
        if not online_laptops:
            logger.info("No online laptops for user %s. Intervention skipped.", user.id)
            return event, False, 0, "Event recorded; no online laptops available."

        # 7. Dispatch intervention over WebSocket to all online laptops
        laptop_ids = [laptop.id for laptop in online_laptops]
        successful_ids = await ws_manager.broadcast_intervention(
            laptop_ids=laptop_ids,
            event_id=str(event.id),
            timestamp=event_time.isoformat(),
        )

        # 8. Record intervention delivery records in DB
        for lid in laptop_ids:
            interv_status = (
                InterventionStatus.SENT.value
                if lid in successful_ids
                else InterventionStatus.FAILED.value
            )
            interv_rec = Intervention(
                event_id=event.id,
                user_id=user.id,
                laptop_device_id=lid,
                sent_at=now,
                status=interv_status,
            )
            session.add(interv_rec)

        await session.commit()

        logger.info(
            "Intervention authorized and dispatched to %d laptop(s) for user %s",
            len(successful_ids),
            user.id,
        )
        return event, True, len(successful_ids), "Intervention successfully dispatched to online laptops."

    @staticmethod
    async def acknowledge_intervention(
        session: AsyncSession,
        event_id: uuid.UUID,
        laptop_device_id: uuid.UUID,
    ) -> bool:
        """Record intervention acknowledgement from laptop."""
        now = utcnow()
        stmt = (
            update(Intervention)
            .where(Intervention.event_id == event_id)
            .where(Intervention.laptop_device_id == laptop_device_id)
            .values(
                acknowledged_at=now,
                status=InterventionStatus.ACKNOWLEDGED.value,
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        logger.info("Acknowledged intervention for event %s on laptop %s", event_id, laptop_device_id)
        return result.rowcount > 0


event_service = EventService()
