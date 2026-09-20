"""NoInsta Laptop Client main application entry point."""

import argparse
import logging
import signal
import sys
import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtWidgets import QApplication

from auth.credentials import CredentialManager
from config import get_app_dir, load_config, setup_logging
from models.config_models import AppConfig
from models.messages import ConnectionState
from network.connection_manager import ConnectionManager
from startup.startup_manager import StartupManager
from ui.analytics_window import AnalyticsWindow
from ui.intervention_window import InterventionWindow
from ui.pairing_dialog import PairingDialog
from ui.tray import SystemTray

logger = logging.getLogger("noinsta")


class NoInstaApplication(QObject):
    """Coordinates lifecycle, UI windows, networking, and system tray."""

    def __init__(self, app: QApplication, config: AppConfig):
        super().__init__()
        self.app = app
        self.config = config

        self.credential_manager = CredentialManager()
        self.connection_manager = ConnectionManager(
            config=self.config,
            credential_manager=self.credential_manager,
        )
        self.startup_manager = StartupManager()

        self._active_intervention: Optional[InterventionWindow] = None
        self._pairing_dialog: Optional[PairingDialog] = None
        self._analytics_window: Optional[AnalyticsWindow] = None

        # Set up System Tray
        self.tray = SystemTray(
            on_test_intervention=self.trigger_test_intervention,
            on_reconnect=self.connection_manager.reconnect,
            on_pair=self.show_pairing_dialog,
            on_quit=self.shutdown,
            on_view_analytics=self.show_analytics_window,
        )

        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect network signals to UI handlers."""
        self.connection_manager.state_changed.connect(self._on_state_changed)
        self.connection_manager.intervention_triggered.connect(self._on_intervention_triggered)
        self.connection_manager.status_message.connect(self._on_status_message)
        self.connection_manager.pairing_required.connect(self._on_pairing_required)

    def start(self, force_pair: bool = False) -> None:
        """Begin application execution."""
        if not force_pair and self.credential_manager.is_paired():
            creds = self.credential_manager.get_credentials()
            device_label = creds.device_name or creds.device_id if creds else "Laptop"
            self.tray.set_device_info(device_label)
            logger.info("Starting with existing device credentials (%s)", creds.device_id if creds else "unknown")
            self.connection_manager.start()
        else:
            logger.info("Device is not paired yet or pairing was requested. Opening pairing dialog...")
            self.tray.set_device_info("Not Paired")
            # Present pairing dialog immediately on launch
            QTimer.singleShot(50, self.show_pairing_dialog)

    def show_pairing_dialog(self) -> None:
        """Display the pairing modal dialog."""
        if self._pairing_dialog and self._pairing_dialog.isVisible():
            self._pairing_dialog.raise_()
            self._pairing_dialog.activateWindow()
            return

        was_paired_before = self.credential_manager.is_paired()

        self._pairing_dialog = PairingDialog(
            request_code_callback=self.connection_manager.request_pairing_code,
            check_status_callback=self.connection_manager.check_pairing_status,
            pair_callback=self.connection_manager.pair_device,
            default_server_url=self.config.server_url,
        )

        result = self._pairing_dialog.exec()
        if result == PairingDialog.DialogCode.Accepted:
            self.credential_manager.mark_as_paired()
            creds = self.credential_manager.get_credentials()
            if creds:
                self.tray.set_device_info(creds.device_name or creds.device_id)
                self.tray.show_notification(
                    "NoInsta Paired",
                    f"Paired successfully as {creds.device_name or creds.device_id}.",
                )
                if not self.connection_manager.is_running:
                    self.connection_manager.start()
        else:
            if not was_paired_before:
                logger.info("Pairing cancelled or closed before completion. Exiting.")
                self.shutdown()
        self._pairing_dialog = None

    def trigger_test_intervention(self) -> None:
        """Trigger a local test intervention without contacting the server."""
        test_event_id = f"test_{int(time.time())}"
        logger.info("Triggering local test intervention (%s)", test_event_id)
        self._on_intervention_triggered(test_event_id, "now")

    def _on_intervention_triggered(self, event_id: str, timestamp: str) -> None:
        """Display intervention window upon server command."""
        # If an intervention window is already showing, avoid duplicate stacking
        if self._active_intervention is not None and self._active_intervention.isVisible():
            logger.info("Intervention window already active. Ignoring secondary trigger: %s", event_id)
            return

        logger.info("Displaying intervention for event: %s (timestamp: %s)", event_id, timestamp)
        self.tray.update_state(ConnectionState.INTERVENTION_ACTIVE.value)

        self._active_intervention = InterventionWindow(
            event_id=event_id,
            config=self.config,
            on_closed_callback=self._on_intervention_closed,
        )
        self._active_intervention.show_attention()

    def _on_intervention_closed(self, event_id: str) -> None:
        """Handle intervention dismissal from user."""
        logger.info("Intervention closed for event: %s", event_id)
        self._active_intervention = None

        if not event_id.startswith("test_"):
            self.connection_manager.notify_intervention_closed(event_id)

    def _on_state_changed(self, state_str: str) -> None:
        """Update system tray on connection state changes."""
        self.tray.update_state(state_str)

    def _on_status_message(self, msg: str) -> None:
        """Log status updates and show relevant notifications."""
        logger.info("Status update: %s", msg)

    def _on_pairing_required(self) -> None:
        """Prompt pairing dialog when server rejects credentials."""
        self.tray.set_device_info("Not Paired")
        self.show_pairing_dialog()

    def show_analytics_window(self) -> None:
        """Display the analytics and telemetry window."""
        if self._analytics_window is None:
            self._analytics_window = AnalyticsWindow(
                fetch_analytics_callback=self.connection_manager.fetch_analytics,
                update_cooldown_callback=self.connection_manager.update_cooldown,
                server_url=self.config.server_url,
            )
        self._analytics_window.show()
        self._analytics_window.raise_()
        self._analytics_window.activateWindow()
        self._analytics_window.refresh_data()

    def shutdown(self) -> None:
        """Gracefully shut down all components."""
        logger.info("Initiating application shutdown...")

        # 1. Close analytics window if open
        if self._analytics_window:
            self._analytics_window.close()
            self._analytics_window = None

        # 2. Close active intervention and terminate media immediately
        if self._active_intervention:
            self._active_intervention.dismiss()
            self._active_intervention = None

        # 3. Stop network manager and background threads
        self.connection_manager.stop()

        # 4. Exit Qt
        self.app.quit()
        logger.info("Application exited.")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="noinsta",
        description="NoInsta Laptop Client - Productivity Control Agent",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Launch application and immediately fire a test intervention.",
    )
    parser.add_argument(
        "--pair",
        action="store_true",
        help="Launch directly into pairing setup dialog (generates a fresh code even if already paired).",
    )
    parser.add_argument(
        "--reset",
        "--unpair",
        dest="reset",
        action="store_true",
        help="Clear stored pairing credentials and reset device registration.",
    )
    parser.add_argument(
        "--enable-autostart",
        action="store_true",
        help="Register NoInsta to start automatically at user login.",
    )
    parser.add_argument(
        "--disable-autostart",
        action="store_true",
        help="Remove NoInsta from automatic user login startup.",
    )
    parser.add_argument(
        "--check-autostart",
        action="store_true",
        help="Check whether autostart is currently enabled.",
    )
    parser.add_argument(
        "--analytics",
        action="store_true",
        help="Open the analytics and telemetry dashboard window.",
    )
    return parser.parse_args()


def main() -> int:
    """Application entry point."""
    args = parse_args()

    # Handle reset/unpair CLI action
    if args.reset:
        mgr = CredentialManager()
        mgr.clear_credentials()
        print("Stored pairing credentials successfully cleared.")
        return 0

    # Handle autostart CLI actions if requested
    if args.enable_autostart:
        mgr = StartupManager()
        success = mgr.enable_autostart()
        print(f"Autostart enabled: {success}")
        return 0 if success else 1

    if args.disable_autostart:
        mgr = StartupManager()
        success = mgr.disable_autostart()
        print(f"Autostart disabled: {success}")
        return 0 if success else 1

    if args.check_autostart:
        mgr = StartupManager()
        enabled = mgr.is_autostart_enabled()
        print(f"Autostart enabled: {enabled}")
        return 0

    # Load configuration & initialize logging
    config = load_config()
    setup_logging(config.log_level)

    logger.info("Starting NoInsta Laptop Client...")

    # Initialize PySide6 GUI Application
    # Setting quitOnLastWindowClosed to False allows background tray operation
    app = QApplication(sys.argv)
    app.setApplicationName("NoInsta")
    app.setOrganizationName("NoInsta")
    app.setQuitOnLastWindowClosed(False)

    client_app = NoInstaApplication(app=app, config=config)

    # Allow Python signal handling for graceful Ctrl+C in terminal
    sig_timer = QTimer()
    sig_timer.start(300)
    sig_timer.timeout.connect(lambda: None)

    signal.signal(signal.SIGINT, lambda sig, frame: client_app.shutdown())
    signal.signal(signal.SIGTERM, lambda sig, frame: client_app.shutdown())

    # Start client (opens pairing dialog if not paired or --pair specified)
    client_app.start(force_pair=args.pair)

    if args.test:
        QTimer.singleShot(300, client_app.trigger_test_intervention)

    if args.analytics:
        QTimer.singleShot(250, client_app.show_analytics_window)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
