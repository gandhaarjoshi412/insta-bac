"""ConnectionManager bridging asyncio network operations with PySide6 GUI thread."""

import asyncio
import logging
from typing import Optional, Tuple

from PySide6.QtCore import QObject, QThread, Signal

from auth.credentials import CredentialManager
from models.config_models import AppConfig
from models.messages import ConnectionState, DeviceCredentials, HeartbeatMessage
from network.api_client import APIClient
from network.heartbeat import HeartbeatManager
from network.websocket_client import WebSocketClient

logger = logging.getLogger(__name__)


class NetworkWorker(QThread):
    """Background QThread running the asyncio event loop for networking."""

    state_changed = Signal(str)
    intervention_triggered = Signal(str, str)
    status_message = Signal(str)
    pairing_required = Signal()

    def __init__(
        self,
        config: AppConfig,
        credential_manager: CredentialManager,
        api_client: APIClient,
    ):
        super().__init__()
        self.config = config
        self.credential_manager = credential_manager
        self.api_client = api_client

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_client: Optional[WebSocketClient] = None
        self._heartbeat: Optional[HeartbeatManager] = None
        self._is_running = True
        self._current_state = ConnectionState.DISCONNECTED

    def _set_state(self, state: ConnectionState) -> None:
        """Update connection state and emit signal."""
        self._current_state = state
        self.state_changed.emit(state.value)

    def run(self) -> None:
        """Execute the background event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Check if already paired
        if not self.credential_manager.is_paired():
            self._set_state(ConnectionState.DISCONNECTED)
            self.pairing_required.emit()
            self.status_message.emit("Device not paired. Pairing code required.")
        else:
            self._set_state(ConnectionState.CONNECTING)

        self._ws_client = WebSocketClient(
            config=self.config,
            credentials_provider=self.credential_manager.get_credentials,
            on_instagram_open=self._on_instagram_open,
            on_auth_error=self._on_auth_error,
            on_connection_change=self._on_connection_change,
        )

        self._heartbeat = HeartbeatManager(
            interval_seconds=self.config.heartbeat_interval_seconds,
            credentials_provider=self.credential_manager.get_credentials,
            send_callback=self._queue_heartbeat,
        )

        try:
            self._loop.run_until_complete(self._main_network_task())
        except Exception as exc:
            if self._is_running:
                logger.error("Error in network worker event loop: %s", exc, exc_info=True)
            else:
                logger.debug("Network worker event loop stopped gracefully: %s", exc)
        finally:
            try:
                # Cancel all remaining tasks in the loop
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._loop.close()
            except Exception as exc:
                logger.debug("Loop cleanup notice: %s", exc)
            logger.info("NetworkWorker thread exited.")

    async def _main_network_task(self) -> None:
        """Main async task coordinating WebSocket and Heartbeat."""
        if self._heartbeat:
            self._heartbeat.start()
        if self._ws_client:
            await self._ws_client.start()

    def _on_instagram_open(self, event_id: str, timestamp: str) -> None:
        """Callback from WebSocketClient when Instagram is opened."""
        self._set_state(ConnectionState.INTERVENTION_ACTIVE)
        self.intervention_triggered.emit(event_id, timestamp)
        self.status_message.emit(f"Intervention triggered for event: {event_id}")

    def _on_auth_error(self, reason: str) -> None:
        """Callback on authentication error."""
        logger.warning("Auth error callback received: %s", reason)
        self._set_state(ConnectionState.DISCONNECTED)
        self.status_message.emit(f"Authentication error: {reason}")
        # Try refreshing tokens
        creds = self.credential_manager.get_credentials()
        if creds and creds.refresh_token:
            success, new_access, new_refresh = self.api_client.refresh_access_token(
                device_id=creds.device_id,
                refresh_token=creds.refresh_token,
            )
            if success and new_access:
                self.credential_manager.update_tokens(new_access, new_refresh)
                self.status_message.emit("Access token refreshed.")
                return

        # If refresh failed or not available, request re-pairing
        self.credential_manager.clear_credentials()
        self.pairing_required.emit()

    def _on_connection_change(self, is_connected: bool) -> None:
        """Callback from WebSocketClient on connection state change."""
        if is_connected:
            self._set_state(ConnectionState.CONNECTED)
            self.status_message.emit("Connected to NoInsta server.")
        else:
            self._set_state(ConnectionState.CONNECTING)
            self.status_message.emit("Disconnected. Reconnecting...")

    def _queue_heartbeat(self, heartbeat: HeartbeatMessage) -> None:
        """Queue a heartbeat message in the WebSocket client."""
        if self._ws_client:
            self._ws_client.queue_message(heartbeat)

    def notify_intervention_closed(self, event_id: str) -> None:
        """Report intervention closed to server (thread-safe)."""
        if self._ws_client and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                self._ws_client.queue_intervention_closed,
                event_id,
            )
        if self._current_state == ConnectionState.INTERVENTION_ACTIVE:
            self._set_state(ConnectionState.CONNECTED)
            self.status_message.emit("Intervention closed.")

    def trigger_reconnect(self) -> None:
        """Request immediate reconnection if loop is active."""
        logger.info("Manual reconnect requested.")
        if self._ws_client and self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._ws_client.stop(), self._loop)

    def stop(self) -> None:
        """Signal thread to stop and terminate event loop."""
        self._is_running = False
        if self._heartbeat:
            self._heartbeat.stop()
        if self._ws_client and self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._ws_client.stop(), self._loop)
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)


class ConnectionManager(QObject):
    """Facade for managing network interactions from the PySide6 UI thread."""

    state_changed = Signal(str)
    intervention_triggered = Signal(str, str)
    status_message = Signal(str)
    pairing_required = Signal()

    def __init__(
        self,
        config: AppConfig,
        credential_manager: CredentialManager,
        api_client: Optional[APIClient] = None,
    ):
        super().__init__()
        self.config = config
        self.credential_manager = credential_manager
        self.api_client = api_client or APIClient(base_url=config.server_url)

        self._worker: Optional[NetworkWorker] = None

    def start(self) -> None:
        """Start the background network worker thread."""
        if self._worker is not None and self._worker.isRunning():
            return

        self._worker = NetworkWorker(
            config=self.config,
            credential_manager=self.credential_manager,
            api_client=self.api_client,
        )

        # Connect signals
        self._worker.state_changed.connect(self.state_changed.emit)
        self._worker.intervention_triggered.connect(self.intervention_triggered.emit)
        self._worker.status_message.connect(self.status_message.emit)
        self._worker.pairing_required.connect(self.pairing_required.emit)

        # Start background worker thread
        self._worker.start()

    @property
    def is_running(self) -> bool:
        """Check if background worker thread is currently active."""
        return self._worker is not None and self._worker.isRunning()

    def request_pairing_code(
        self, device_name: Optional[str] = None
    ) -> Tuple[bool, Optional[str], str]:
        """Request the server to generate a 6-character pairing code for this laptop.
        
        Saves issued credentials, connects background network worker,
        and returns (success, pairing_code, message).
        """
        success, gen_resp, credentials, message = self.api_client.request_pairing_code(
            device_name=device_name
        )
        if success and gen_resp and credentials:
            self.credential_manager.save_credentials(credentials)
            self.status_message.emit(f"Pairing code generated: {gen_resp.pairing_code}")
            if self._worker and self._worker.isRunning():
                self._worker.trigger_reconnect()
            else:
                self.start()
            return True, gen_resp.pairing_code, message
        return False, None, message

    def check_pairing_status(
        self, pairing_code: str
    ) -> Tuple[bool, bool, Optional[str], str]:
        """Check if Android phone has claimed the pairing code."""
        success, is_claimed, claimed_name, msg = self.api_client.check_pairing_status(pairing_code)
        if success and is_claimed:
            self.credential_manager.mark_as_paired()
        return success, is_claimed, claimed_name, msg

    def pair_device(
        self, pairing_code: str, device_name: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Pair this device using a pairing code. Returns (success, message)."""
        success, credentials, message = self.api_client.pair_device(
            pairing_code=pairing_code,
            device_name=device_name,
        )

        if success and credentials:
            self.credential_manager.save_credentials(credentials)
            self.status_message.emit("Device paired successfully. Connecting...")
            # Trigger reconnection with fresh credentials
            if self._worker and self._worker.isRunning():
                self._worker.trigger_reconnect()
            else:
                self.start()
            return True, message
        else:
            return False, message

    def notify_intervention_closed(self, event_id: str) -> None:
        """Notify server that intervention was dismissed."""
        if self._worker:
            self._worker.notify_intervention_closed(event_id)

    def reconnect(self) -> None:
        """Trigger reconnection."""
        if self._worker:
            self._worker.trigger_reconnect()

    def stop(self) -> None:
        """Gracefully stop background network worker."""
        if self._worker:
            self._worker.stop()
            self._worker.quit()
            self._worker.wait(3000)
            self._worker = None
        logger.info("ConnectionManager stopped.")

    def fetch_analytics(self) -> Tuple[bool, Optional[dict], str]:
        """Fetch analytics report from the server using current credentials."""
        creds = self.credential_manager.get_credentials()
        if not creds or not creds.access_token:
            return False, None, "Device not paired or missing access credentials."

        success, data, msg = self.api_client.get_analytics(creds.access_token)
        if not success and "Unauthorized" in msg and creds.refresh_token:
            logger.info("Access token expired while fetching analytics, attempting refresh...")
            refreshed, new_access, new_refresh = self.api_client.refresh_access_token(
                creds.device_id, creds.refresh_token
            )
            if refreshed and new_access:
                self.credential_manager.update_tokens(new_access, new_refresh or creds.refresh_token)
                return self.api_client.get_analytics(new_access)
        return success, data, msg

    def fetch_settings(self) -> Tuple[bool, Optional[dict], str]:
        """Fetch user settings from server."""
        creds = self.credential_manager.get_credentials()
        if not creds or not creds.access_token:
            return False, None, "Device not paired or missing credentials."

        success, data, msg = self.api_client.get_settings(creds.access_token)
        if not success and "Unauthorized" in msg and creds.refresh_token:
            refreshed, new_access, new_refresh = self.api_client.refresh_access_token(
                creds.device_id, creds.refresh_token
            )
            if refreshed and new_access:
                self.credential_manager.update_tokens(new_access, new_refresh or creds.refresh_token)
                return self.api_client.get_settings(new_access)
        return success, data, msg

    def update_cooldown(self, cooldown_seconds: int) -> Tuple[bool, Optional[dict], str]:
        """Update cooldown duration on server."""
        creds = self.credential_manager.get_credentials()
        if not creds or not creds.access_token:
            return False, None, "Device not paired or missing credentials."

        success, data, msg = self.api_client.update_settings(creds.access_token, cooldown_seconds)
        if not success and "Unauthorized" in msg and creds.refresh_token:
            refreshed, new_access, new_refresh = self.api_client.refresh_access_token(
                creds.device_id, creds.refresh_token
            )
            if refreshed and new_access:
                self.credential_manager.update_tokens(new_access, new_refresh or creds.refresh_token)
                return self.api_client.update_settings(new_access, cooldown_seconds)
        return success, data, msg
