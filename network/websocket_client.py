"""Authenticated, resilient WebSocket client for NoInsta client."""

import asyncio
import inspect
import logging
import random
import ssl
import time
from typing import Callable, Dict, List, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from models.config_models import AppConfig
from models.messages import (
    AuthenticateMessage,
    AuthenticatedMessage,
    AuthErrorMessage,
    ErrorMessage,
    BaseInboundMessage,
    BaseOutboundMessage,
    DeviceCredentials,
    HeartbeatAckMessage,
    HeartbeatMessage,
    InboundMessageType,
    InstagramOpenMessage,
    InterventionClosedMessage,
    InterventionReceivedMessage,
    PingMessage,
    current_utc_iso,
    parse_inbound_message,
)

logger = logging.getLogger(__name__)

BACKOFF_DELAYS = [1, 2, 4, 8, 16, 30, 60]


class EventDeduplicator:
    """Maintains an in-memory window of processed event IDs to ignore duplicates."""

    def __init__(self, window_seconds: int = 600):
        self.window_seconds = window_seconds
        self._seen_events: Dict[str, float] = {}

    def is_duplicate(self, event_id: str) -> bool:
        """Check if an event_id was already seen recently; record if new."""
        now = time.monotonic()
        self._cleanup(now)
        if event_id in self._seen_events:
            return True
        self._seen_events[event_id] = now
        return False

    def _cleanup(self, now: float) -> None:
        """Remove events older than the window duration."""
        cutoff = now - self.window_seconds
        expired = [eid for eid, ts in self._seen_events.items() if ts < cutoff]
        for eid in expired:
            del self._seen_events[eid]


def is_ws_open(ws: Any) -> bool:
    """Check if websocket connection is currently open across websockets versions."""
    if ws is None:
        return False
    if hasattr(ws, "state"):
        try:
            return ws.state.name == "OPEN"
        except Exception:
            pass
    if hasattr(ws, "open"):
        return bool(ws.open)
    if hasattr(ws, "closed"):
        return not ws.closed
    return True


class WebSocketClient:
    """Maintains an outbound, authenticated TLS WebSocket connection to NoInsta server."""

    def __init__(
        self,
        config: AppConfig,
        credentials_provider: Callable[[], Optional[DeviceCredentials]],
        on_instagram_open: Callable[[str, str], None],
        on_auth_error: Callable[[str], None],
        on_connection_change: Callable[[bool], None],
    ):
        self.config = config
        self.credentials_provider = credentials_provider
        self.on_instagram_open = on_instagram_open
        self.on_auth_error = on_auth_error
        self.on_connection_change = on_connection_change

        self._running = False
        self._ws: Any = None
        self._outgoing_queue: asyncio.Queue[BaseOutboundMessage] = asyncio.Queue()
        self._pending_closed_acks: List[InterventionClosedMessage] = []
        self._deduplicator = EventDeduplicator(window_seconds=config.dedup_window_seconds)

        self._current_reconnect_index = 0
        self._send_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        """Check if websocket is currently connected and open."""
        return is_ws_open(self._ws)

    async def start(self) -> None:
        """Start the persistent connection loop."""
        self._running = True
        logger.info("Starting WebSocket connection manager loop")

        while self._running:
            credentials = self.credentials_provider()
            if not credentials or not credentials.access_token:
                logger.debug("No credentials available yet. Waiting before retry...")
                await asyncio.sleep(2)
                continue

            ws_url = self.config.get_effective_ws_url(device_id=credentials.device_id)
            logger.info("Connecting outbound WebSocket to %s", ws_url)

            connected_successfully = False
            try:
                # Configure strict TLS context
                ssl_context = ssl.create_default_context()

                headers = {
                    "Authorization": f"Bearer {credentials.access_token}",
                    "X-Device-Id": credentials.device_id,
                }

                connect_kwargs = {
                    "ssl": ssl_context if ws_url.startswith("wss://") else None,
                    "ping_interval": 30,
                    "ping_timeout": None,
                    "close_timeout": None,
                }
                # Support websockets >=14.0 (additional_headers) and <14.0 (extra_headers)
                try:
                    sig = inspect.signature(websockets.connect)
                    if "additional_headers" in sig.parameters:
                        connect_kwargs["additional_headers"] = headers
                    elif "extra_headers" in sig.parameters:
                        connect_kwargs["extra_headers"] = headers
                except Exception:
                    connect_kwargs["additional_headers"] = headers

                async with websockets.connect(
                    ws_url,
                    **connect_kwargs,
                ) as ws:
                    self._ws = ws
                    self._current_reconnect_index = 0
                    connected_successfully = True
                    logger.info("WebSocket connected. Performing authentication handshake...")

                    # Send explicit authentication message
                    auth_msg = AuthenticateMessage(
                        device_id=credentials.device_id,
                        access_token=credentials.access_token,
                    )
                    await ws.send(auth_msg.model_dump_json())

                    # Notify connection established
                    self.on_connection_change(True)

                    # Flush any queued intervention acknowledgements from previous offline state
                    await self._flush_pending_acks(ws)

                    # Start concurrent sender and receiver tasks
                    self._send_task = asyncio.create_task(self._send_loop(ws))
                    self._receive_task = asyncio.create_task(self._receive_loop(ws))

                    done, pending = await asyncio.wait(
                        [self._send_task, self._receive_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                    # Retrieve exceptions from completed tasks to avoid 'Task exception was never retrieved'
                    for task in done:
                        if not task.cancelled():
                            exc = task.exception()
                            if isinstance(exc, ConnectionClosed) and exc.code == 1008:
                                logger.warning("Server rejected authentication (code 1008). Prompting pairing.")
                                self.on_auth_error("Authentication rejected by server (code 1008)")
                                break

            except ConnectionClosed as exc:
                logger.warning("WebSocket closed by server (code=%s, reason=%s)", exc.code, exc.reason)
                if exc.code == 1008:
                    logger.warning("Server rejected authentication (code 1008). Prompting pairing.")
                    self.on_auth_error("Authentication rejected by server (code 1008)")
                    break
            except WebSocketException as exc:
                logger.warning("WebSocket error encountered: %s", exc)
            except OSError as exc:
                logger.warning("Network connection failed: %s", exc)
            except Exception as exc:
                logger.error("Unexpected error in WebSocket connection loop: %s", exc, exc_info=True)
            finally:
                self._ws = None
                if connected_successfully:
                    self.on_connection_change(False)

            if not self._running:
                break

            # Exponential backoff calculation
            delay = BACKOFF_DELAYS[min(self._current_reconnect_index, len(BACKOFF_DELAYS) - 1)]
            delay = min(delay, self.config.reconnect_max_delay_seconds)
            # Add up to 20% random jitter to avoid thundering herds
            jitter = delay * random.uniform(0.0, 0.2)
            reconnect_wait = delay + jitter

            self._current_reconnect_index += 1
            logger.info(
                "Reconnect scheduled in %.1f seconds (attempt %d)",
                reconnect_wait,
                self._current_reconnect_index,
            )
            await asyncio.sleep(reconnect_wait)

    async def _send_loop(self, ws: Any) -> None:
        """Loop to forward queued outbound messages through WebSocket."""
        while self._running and is_ws_open(ws):
            try:
                # Wait for next message from queue
                message = await self._outgoing_queue.get()
                payload = message.model_dump_json()
                await ws.send(payload)
                self._outgoing_queue.task_done()
                logger.debug("Sent outbound message: %s", message.type)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error sending outbound message: %s", exc)
                # If it was an intervention close message, save to pending acks
                if isinstance(message, InterventionClosedMessage):
                    self._pending_closed_acks.append(message)
                break

    async def _receive_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        """Loop to receive and dispatch messages from server."""
        async for raw_message in ws:
            try:
                parsed = parse_inbound_message(raw_message)
                if parsed is None:
                    continue

                if isinstance(parsed, InstagramOpenMessage):
                    if self._deduplicator.is_duplicate(parsed.event_id):
                        logger.info("Ignoring duplicate intervention event: %s", parsed.event_id)
                        continue

                    logger.info("Instagram intervention received for event: %s", parsed.event_id)
                    # Acknowledge receipt
                    credentials = self.credentials_provider()
                    if credentials:
                        ack = InterventionReceivedMessage(
                            event_id=parsed.event_id,
                            device_id=credentials.device_id,
                        )
                        self.queue_message(ack)

                    # Trigger intervention UI callback
                    self.on_instagram_open(parsed.event_id, parsed.timestamp or current_utc_iso())

                elif isinstance(parsed, PingMessage):
                    logger.debug("Received ping from server; sending heartbeat response")
                    credentials = self.credentials_provider()
                    if credentials:
                        self.queue_message(HeartbeatMessage(device_id=credentials.device_id))

                elif isinstance(parsed, HeartbeatAckMessage):
                    logger.debug("Received heartbeat ack from server")

                elif isinstance(parsed, AuthenticatedMessage):
                    logger.info("Server confirmed authentication: %s", parsed.detail or "OK")

                elif isinstance(parsed, (AuthErrorMessage, ErrorMessage)):
                    reason = getattr(parsed, "detail", None) or getattr(parsed, "reason", None) or "Authentication error"
                    logger.warning("Server error / authentication rejected: %s", reason)
                    self.on_auth_error(reason)

            except Exception as exc:
                logger.error("Error processing inbound message: %s", exc)

    async def _flush_pending_acks(self, ws: Any) -> None:
        """Send any intervention acknowledgements that failed during network outage."""
        if not self._pending_closed_acks:
            return

        logger.info("Flushing %d pending intervention close acknowledgments...", len(self._pending_closed_acks))
        while self._pending_closed_acks:
            ack = self._pending_closed_acks.pop(0)
            try:
                await ws.send(ack.model_dump_json())
                logger.info("Flushed pending intervention close ack: %s", ack.event_id)
            except Exception as exc:
                logger.warning("Failed to flush ack %s (%s). Re-queuing.", ack.event_id, exc)
                self._pending_closed_acks.insert(0, ack)
                break

    def queue_message(self, message: BaseOutboundMessage) -> None:
        """Thread-safe queueing of an outbound message."""
        try:
            self._outgoing_queue.put_nowait(message)
        except Exception as exc:
            logger.error("Failed to queue message %s: %s", message.type, exc)
            if isinstance(message, InterventionClosedMessage):
                self._pending_closed_acks.append(message)

    def queue_intervention_closed(self, event_id: str) -> None:
        """Queue an intervention closed event, ensuring it is preserved if disconnected."""
        credentials = self.credentials_provider()
        device_id = credentials.device_id if credentials else "unknown_device"
        msg = InterventionClosedMessage(event_id=event_id, device_id=device_id)

        if not self.is_connected:
            logger.info("Offline: buffering intervention closed ack for event %s", event_id)
            self._pending_closed_acks.append(msg)
        else:
            self.queue_message(msg)

    async def stop(self) -> None:
        """Cleanly terminate the client and tasks."""
        self._running = False
        if self._send_task:
            self._send_task.cancel()
        if self._receive_task:
            self._receive_task.cancel()
        if is_ws_open(self._ws):
            try:
                await self._ws.close()
            except Exception:
                pass
        logger.info("WebSocketClient stopped cleanly.")
