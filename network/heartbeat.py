"""Periodic background heartbeat scheduler for NoInsta client."""

import asyncio
import logging
from typing import Callable, Optional

from models.messages import DeviceCredentials, HeartbeatMessage

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """Manages periodic transmission of heartbeat beacons over active WebSocket."""

    def __init__(
        self,
        interval_seconds: int,
        credentials_provider: Callable[[], Optional[DeviceCredentials]],
        send_callback: Callable[[HeartbeatMessage], None],
    ):
        self.interval_seconds = interval_seconds
        self.credentials_provider = credentials_provider
        self.send_callback = send_callback
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Start heartbeat loop if not already running."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Heartbeat manager started (interval: %ds)", self.interval_seconds)

    async def _loop(self) -> None:
        """Periodic heartbeat loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break

                creds = self.credentials_provider()
                if creds and creds.device_id:
                    heartbeat = HeartbeatMessage(device_id=creds.device_id)
                    self.send_callback(heartbeat)
                    logger.debug("Heartbeat queued for device: %s", creds.device_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unexpected error in heartbeat loop: %s", exc)

    def stop(self) -> None:
        """Stop the heartbeat scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Heartbeat manager stopped.")
