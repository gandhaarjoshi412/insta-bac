"""WebSocket endpoint handling persistent, authenticated laptop client connections."""

import json
import logging
from typing import Optional
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import decode_access_token
from app.models.device import Device, DeviceType
from app.schemas.websocket import (
    MessageType,
    WSAuthMessage,
    WSAuthenticatedMessage,
    WSErrorMessage,
    WSHeartbeatAckMessage,
)
from app.services.event_service import event_service
from app.services.presence_service import presence_service
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


async def authenticate_ws_connection(
    websocket: WebSocket, device_id_param: Optional[str] = None
) -> Optional[Device]:
    """Authenticate incoming WebSocket via query param, header, or initial message."""
    token: Optional[str] = None

    # 1. Try query parameter ?token=...
    token = websocket.query_params.get("token")

    # 2. Try Authorization header
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

    # 3. If not in handshake headers, await initial authenticate JSON message
    if not token:
        try:
            raw_init = await websocket.receive_text()
            data = json.loads(raw_init)
            if data.get("type") == MessageType.AUTHENTICATE.value:
                auth_msg = WSAuthMessage.model_validate(data)
                token = auth_msg.access_token
        except Exception as exc:
            logger.warning("Failed to receive initial auth message: %s", exc)
            return None

    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        logger.warning("WebSocket auth rejected: invalid or expired token.")
        return None

    dev_id_str = payload.get("device_id")
    if not dev_id_str:
        logger.warning("WebSocket auth rejected: token has no device_id.")
        return None

    try:
        dev_uuid = uuid.UUID(dev_id_str)
    except ValueError:
        return None

    # If route has explicit device_id parameter, ensure match
    if device_id_param:
        try:
            param_uuid = uuid.UUID(device_id_param)
            if param_uuid != dev_uuid:
                logger.warning("WebSocket device_id param mismatch: %s != %s", param_uuid, dev_uuid)
                return None
        except ValueError:
            return None

    # Verify device in database
    async with async_session_factory() as session:
        stmt = select(Device).where(Device.id == dev_uuid)
        device = (await session.execute(stmt)).scalar_one_or_none()

        if not device or not device.is_active:
            logger.warning("WebSocket auth rejected: device %s not found or revoked.", dev_uuid)
            return None

        # Ensure device is LAPTOP
        if device.device_type != DeviceType.LAPTOP.value:
            logger.warning("WebSocket auth rejected: device %s is not a LAPTOP.", dev_uuid)
            return None

        return device


@router.websocket("/ws/laptop")
@router.websocket("/ws/device/{device_id}")
async def laptop_websocket_endpoint(websocket: WebSocket, device_id: Optional[str] = None):
    """Maintain persistent authenticated WebSocket connection for a laptop client."""
    await websocket.accept()

    device = await authenticate_ws_connection(websocket, device_id_param=device_id)
    if not device:
        err = WSErrorMessage(detail="Authentication failed. Connection rejected.")
        try:
            await websocket.send_text(err.model_dump_json())
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    # Register in WebSocketManager (safely closes any previous connection for this device)
    await ws_manager.connect(device.id, device.user_id, websocket)

    # Record initial presence heartbeat
    async with async_session_factory() as session:
        await presence_service.record_heartbeat(session, device.id)

    # Send authenticated confirmation
    auth_ack = WSAuthenticatedMessage(
        device_id=str(device.id),
        user_id=str(device.user_id),
    )
    await websocket.send_text(auth_ack.model_dump_json())

    logger.info("Laptop %s connected and authenticated via WebSocket.", device.id)

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                logger.warning("Malformed JSON from laptop %s: %s", device.id, raw_text[:50])
                continue

            if not isinstance(data, dict):
                continue

            msg_type = data.get("type")

            # 1. Heartbeat
            if msg_type == MessageType.HEARTBEAT.value:
                async with async_session_factory() as session:
                    await presence_service.record_heartbeat(session, device.id)
                ack = WSHeartbeatAckMessage()
                await websocket.send_text(ack.model_dump_json())
                logger.debug("Received heartbeat and replied ack for laptop %s", device.id)

            # 2. Intervention Closed Acknowledgement
            elif msg_type == MessageType.INTERVENTION_CLOSED.value:
                event_id_str = data.get("event_id")
                if event_id_str:
                    try:
                        event_uuid = uuid.UUID(event_id_str)
                        async with async_session_factory() as session:
                            await event_service.acknowledge_intervention(
                                session=session,
                                event_id=event_uuid,
                                laptop_device_id=device.id,
                            )
                        logger.info("Intervention closed for event %s on laptop %s", event_id_str, device.id)
                    except ValueError:
                        logger.warning("Malformed event_id in intervention_closed: %s", event_id_str)

            # 3. Intervention Received Notice
            elif msg_type == MessageType.INTERVENTION_RECEIVED.value:
                logger.debug("Intervention received notice from laptop %s for event %s", device.id, data.get("event_id"))

            # 4. Unknown/Unsupported commands
            else:
                logger.warning("Unknown WebSocket message type %s from laptop %s", msg_type, device.id)

    except WebSocketDisconnect:
        logger.info("Laptop %s disconnected.", device.id)
    except Exception as exc:
        logger.error("Error in laptop %s WebSocket loop: %s", device.id, exc)
    finally:
        await ws_manager.disconnect(device.id, device.user_id)
