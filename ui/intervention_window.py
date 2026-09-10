"""Attention-grabbing intervention window for NoInsta."""

import logging
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import resolve_asset_path
from models.config_models import AppConfig
from ui.media_player import MediaManager

logger = logging.getLogger(__name__)


class InterventionWindow(QDialog):
    """Attention-grabbing modal window displayed when Instagram is opened."""

    def __init__(
        self,
        event_id: str,
        config: AppConfig,
        on_closed_callback: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.event_id = event_id
        self.config = config
        self.on_closed_callback = on_closed_callback
        self.media_manager = MediaManager(self)
        self._is_dismissed = False

        self._init_window_flags()
        self._init_ui()
        self._start_media()

    def _init_window_flags(self) -> None:
        """Set cross-platform window flags compatible with X11, Wayland, and Windows."""
        flags = Qt.WindowType.Dialog
        if self.config.window.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.setWindowTitle(self.config.window.title)
        self.setModal(True)
        self.resize(self.config.window.width, self.config.window.height)

    def _init_ui(self) -> None:
        """Construct the intervention user interface."""
        # Dark, attention-grabbing styling
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                border: 3px solid #E1306C;
                border-radius: 12px;
            }
            QLabel#HeadlineLabel {
                color: #FFFFFF;
                font-weight: 900;
                font-size: 26px;
                letter-spacing: 1.5px;
            }
            QLabel#SubheadLabel {
                color: #FF5252;
                font-weight: bold;
                font-size: 15px;
            }
            QPushButton#CloseButton {
                background-color: #E1306C;
                color: #FFFFFF;
                font-size: 16px;
                font-weight: bold;
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
            }
            QPushButton#CloseButton:hover {
                background-color: #C13584;
            }
            QPushButton#CloseButton:pressed {
                background-color: #833AB4;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 1. Headline Banner
        headline = QLabel(self.config.window.headline)
        headline.setObjectName("HeadlineLabel")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(headline)

        # 2. Media Area (Video > Image > Text Fallback)
        media_container = self._build_media_widget()
        layout.addWidget(media_container, stretch=1)

        # 3. Subheading / Warning Text
        subhead = QLabel(self.config.window.subheading)
        subhead.setObjectName("SubheadLabel")
        subhead.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subhead.setWordWrap(True)
        layout.addWidget(subhead)

        # 4. Action Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.close_btn = QPushButton(self.config.window.button_text)
        self.close_btn.setObjectName("CloseButton")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.dismiss)
        btn_layout.addWidget(self.close_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Shortcuts: Enter, Space, Escape to dismiss
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, self.dismiss)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.dismiss)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.dismiss)

        # Ensure close button gets initial focus
        self.close_btn.setFocus()

    def _build_media_widget(self) -> QWidget:
        """Create media presentation widget (Video or Image or Fallback Label)."""
        # Try Video first if configured
        video_path = resolve_asset_path(self.config.media.video_path)
        if video_path:
            video_widget = self.media_manager.setup_video(
                video_path=video_path,
                loop=self.config.media.loop_video,
            )
            if video_widget is not None:
                video_widget.setStyleSheet("background-color: #000000; border-radius: 8px;")
                return video_widget

        # Try Image
        image_path = resolve_asset_path(self.config.media.image_path)
        if image_path:
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                img_label = QLabel()
                img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                # Scale smoothly within dialog bounds
                scaled = pixmap.scaled(
                    400,
                    280,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                img_label.setPixmap(scaled)
                return img_label
            else:
                logger.warning("Image file %s could not be decoded by Qt", image_path)

        # Fallback Text/Icon banner if media not found
        fallback_label = QLabel("⚠️\n\nINSTAGRAM DETECTED\nPUT YOUR PHONE AWAY")
        fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fallback_label.setStyleSheet("""
            QLabel {
                color: #FFA726;
                font-size: 20px;
                font-weight: bold;
                border: 2px dashed #FFA726;
                border-radius: 8px;
                padding: 20px;
                background-color: #1E1E1E;
            }
        """)
        return fallback_label

    def _start_media(self) -> None:
        """Trigger configured background audio playback."""
        audio_path = resolve_asset_path(self.config.media.audio_path)
        if audio_path:
            self.media_manager.play_audio(
                audio_path=audio_path,
                loop=self.config.media.loop_audio,
            )

    def dismiss(self) -> None:
        """Stop media, close window, and send intervention acknowledgment."""
        if self._is_dismissed:
            return
        self._is_dismissed = True

        logger.info("Intervention dismissed by user for event: %s", self.event_id)

        # 1. Stop audio and video immediately
        self.media_manager.stop_all()

        # 2. Close UI
        self.accept()

        # 3. Report closure to server callback
        try:
            self.on_closed_callback(self.event_id)
        except Exception as exc:
            logger.error("Error executing intervention on_closed_callback: %s", exc)

    def closeEvent(self, event) -> None:
        """Ensure media is stopped even if window is closed via window manager X button."""
        self.dismiss()
        super().closeEvent(event)

    def show_attention(self) -> None:
        """Display window and request user attention across desktop environments."""
        self.show()
        self.raise_()
        self.activateWindow()
