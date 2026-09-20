"""System Tray integration for NoInsta background operation."""

import logging
import os
import platform
import subprocess
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config import get_app_dir
from models.messages import ConnectionState

logger = logging.getLogger(__name__)


def create_tray_pixmap(color_hex: str) -> QPixmap:
    """Dynamically render a clean status icon pixmap."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Outer circle
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 24, 24)

    # Inner letter 'N'
    painter.setPen(QColor("#FFFFFF"))
    font = painter.font()
    font.setPixelSize(16)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "N")

    painter.end()
    return pixmap


class SystemTray(QObject):
    """System tray icon and context menu."""

    def __init__(
        self,
        on_test_intervention: Callable[[], None],
        on_reconnect: Callable[[], None],
        on_pair: Callable[[], None],
        on_quit: Callable[[], None],
        on_view_analytics: Optional[Callable[[], None]] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.on_test_intervention = on_test_intervention
        self.on_reconnect = on_reconnect
        self.on_pair = on_pair
        self.on_quit = on_quit
        self.on_view_analytics = on_view_analytics

        self.tray_icon = QSystemTrayIcon(self)
        self._current_state = ConnectionState.DISCONNECTED
        self._device_info = "Not Paired"

        self._init_menu()
        self.update_state(ConnectionState.DISCONNECTED.value)
        if self.on_view_analytics:
            self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.on_view_analytics:
                self.on_view_analytics()

    def _init_menu(self) -> None:
        """Create tray context menu."""
        menu = QMenu()

        self.title_action = QAction("NoInsta", self)
        self.title_action.setEnabled(False)
        menu.addAction(self.title_action)

        self.status_action = QAction("Status: Disconnected", self)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)

        self.device_action = QAction("Device: Unknown", self)
        self.device_action.setEnabled(False)
        menu.addAction(self.device_action)

        menu.addSeparator()

        if self.on_view_analytics:
            analytics_action = QAction("📊 View Analytics & Telemetry", self)
            analytics_action.triggered.connect(self.on_view_analytics)
            menu.addAction(analytics_action)

        test_action = QAction("⚡ Test Intervention", self)
        test_action.triggered.connect(self.on_test_intervention)
        menu.addAction(test_action)

        reconnect_action = QAction("🔄 Reconnect", self)
        reconnect_action.triggered.connect(self.on_reconnect)
        menu.addAction(reconnect_action)

        pair_action = QAction("🔑 Pair Device...", self)
        pair_action.triggered.connect(self.on_pair)
        menu.addAction(pair_action)

        open_config_action = QAction("📁 Open Config Folder", self)
        open_config_action.triggered.connect(self._open_config_dir)
        menu.addAction(open_config_action)

        menu.addSeparator()

        quit_action = QAction("❌ Quit NoInsta", self)
        quit_action.triggered.connect(self.on_quit)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)

    def set_device_info(self, info: str) -> None:
        """Update device information displayed in tray menu."""
        self._device_info = info
        self.device_action.setText(f"Device: {info}")

    def update_state(self, state_str: str) -> None:
        """Update tray icon color and status text based on application state."""
        try:
            state = ConnectionState(state_str)
        except ValueError:
            state = ConnectionState.DISCONNECTED

        self._current_state = state

        if state == ConnectionState.CONNECTED:
            color = "#4CAF50"  # Green
            text = "Connected (Online)"
        elif state == ConnectionState.CONNECTING:
            color = "#FF9800"  # Orange
            text = "Connecting..."
        elif state == ConnectionState.AUTHENTICATING:
            color = "#2196F3"  # Blue
            text = "Authenticating..."
        elif state == ConnectionState.INTERVENTION_ACTIVE:
            color = "#E91E63"  # Pink / Magenta
            text = "Intervention Active!"
        else:
            color = "#9E9E9E"  # Grey
            text = "Disconnected"

        self.status_action.setText(f"Status: {text}")
        self.tray_icon.setToolTip(f"NoInsta - {text}")
        icon = QIcon(create_tray_pixmap(color))
        self.tray_icon.setIcon(icon)

    def show_notification(self, title: str, message: str) -> None:
        """Display desktop balloon notification from tray icon."""
        self.tray_icon.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _open_config_dir(self) -> None:
        """Open the application configuration directory in native file manager."""
        folder = get_app_dir()
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(folder)
            elif system == "Darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            logger.error("Failed to open config directory: %s", exc)
