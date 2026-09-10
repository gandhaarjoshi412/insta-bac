"""WebSocket Connection Manager for active laptop clients."""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Set
import uuid

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Maintains active laptop WebSocket connections indexed by device ID and user ID."""

    def __init__(self):
        # Map: device_id -> WebSocket
        self._connections: Dict[uuid.UUID, WebSocket] = {}
        # Map: user_id -> Set[device_id]
        self._user_laptops: Dict[uuid.UUID, Set[uuid.UUID]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        device_id: uuid.UUID,
        user_id: uuid.UUID,
        websocket: WebSocket,
    ) -> None:
        """Register newly authenticated WebSocket connection.
        
        If an old connection exists for this device, it is cleanly closed first.
        """
        async with self._lock:
            # Clean up previous connection for same device if present (stale connection prevention)
            if device_id in self._connections:
                old_ws = self._connections[device_id]
                try:
                    logger.info("Closing stale WebSocket connection for device %s", device_id)
                    await old_ws.close(code=1000, reason="Replaced by new connection")
                except Exception as exc:
                    logger.debug("Notice closing stale connection: %s", exc)

            self._connections[device_id] = websocket
            if user_id not in self._user_laptops:
                self._user_laptops[user_id] = set()
            self._user_laptops[user_id].add(device_id)

            logger.info(
                "Laptop device %s (user %s) registered in WebSocketManager. Active connections: %d",
                device_id,
                user_id,
                len(self._connections),
            )

    async def disconnect(self, device_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> None:
        """Unregister a disconnected WebSocket."""
        async with self._lock:
            if device_id in self._connections:
                del self._connections[device_id]

            if user_id and user_id in self._user_laptops:
                self._user_laptops[user_id].discard(device_id)
                if not self._user_laptops[user_id]:
                    del self._user_laptops[user_id]
            else:
                # Search and remove from user map
                for uid, devices in list(self._user_laptops.items()):
                    if device_id in devices:
                        devices.discard(device_id)
                        if not devices:
                            del self._user_laptops[uid]

            logger.info(
                "Laptop device %s removed from WebSocketManager. Remaining: %d",
                device_id,
                len(self._connections),
            )

    def is_connected(self, device_id: uuid.UUID) -> bool:
        """Check whether an active WebSocket connection currently exists for device."""
        return device_id in self._connections

    def get_user_connected_laptops(self, user_id: uuid.UUID) -> List[uuid.UUID]:
        """Return list of connected device IDs for a user."""
        device_ids = self._user_laptops.get(user_id, set())
        return [did for did in device_ids if did in self._connections]

    async def send_message(self, device_id: uuid.UUID, message_dict: dict) -> bool:
        """Send JSON payload to specific laptop client."""
        ws = self._connections.get(device_id)
        if not ws:
            return False

        try:
            payload = json.dumps(message_dict)
            await ws.send_text(payload)
            return True
        except Exception as exc:
            logger.warning("Failed to send message to device %s: %s", device_id, exc)
            return False

    async def broadcast_intervention(
        self,
        laptop_ids: List[uuid.UUID],
        event_id: str,
        timestamp: str,
    ) -> List[uuid.UUID]:
        """Broadcast instagram_open intervention command to online laptops.
        
        Returns list of device IDs that successfully received the message.
        """
        payload = {
            "type": "instagram_open",
            "event_id": str(event_id),
            "timestamp": timestamp,
        }

        successful_deliveries: List[uuid.UUID] = []
        for did in laptop_ids:
            sent = await self.send_message(did, payload)
            if sent:
                successful_deliveries.append(did)
                logger.info("Dispatched intervention %s to laptop %s", event_id, did)
            else:
                logger.warning("Failed to dispatch intervention to laptop %s", did)

        return successful_deliveries


ws_manager = WebSocketManager()
