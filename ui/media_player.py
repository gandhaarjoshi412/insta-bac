"""Local audio and video media playback for NoInsta intervention."""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

logger = logging.getLogger(__name__)


class MediaManager(QObject):
    """Manages audio and video playback for the intervention window."""

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._audio_player: Optional[QMediaPlayer] = None
        self._audio_output: Optional[QAudioOutput] = None
        self._video_player: Optional[QMediaPlayer] = None
        self._video_widget: Optional[QVideoWidget] = None

    def play_audio(self, audio_path: Optional[Path], loop: bool = True) -> bool:
        """Start playing local audio file with optional looping.
        
        Returns True if playback initiated, False if missing or error.
        """
        self.stop_audio()

        if not audio_path or not audio_path.exists():
            logger.warning("Intervention audio not played: file not found (%s)", audio_path)
            return False

        try:
            self._audio_player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._audio_player.setAudioOutput(self._audio_output)
            self._audio_output.setVolume(1.0)

            if loop:
                self._audio_player.setLoops(QMediaPlayer.Loops.Infinite)

            url = QUrl.fromLocalFile(str(audio_path.resolve()))
            self._audio_player.setSource(url)
            self._audio_player.play()
            logger.info("Playing intervention audio from %s", audio_path)
            return True
        except Exception as exc:
            logger.error("Failed to initialize audio playback: %s", exc)
            self.stop_audio()
            return False

    def setup_video(
        self, video_path: Optional[Path], loop: bool = True
    ) -> Optional[QVideoWidget]:
        """Initialize and return a video widget playing the local video.
        
        Returns QVideoWidget if successful, None if missing or unsupported.
        """
        self.stop_video()

        if not video_path or not video_path.exists():
            logger.warning("Intervention video not loaded: file not found (%s)", video_path)
            return None

        try:
            self._video_widget = QVideoWidget()
            self._video_player = QMediaPlayer(self)
            self._video_player.setVideoOutput(self._video_widget)

            if loop:
                self._video_player.setLoops(QMediaPlayer.Loops.Infinite)

            url = QUrl.fromLocalFile(str(video_path.resolve()))
            self._video_player.setSource(url)
            self._video_player.play()
            logger.info("Playing intervention video from %s", video_path)
            return self._video_widget
        except Exception as exc:
            logger.error("Failed to initialize video playback: %s", exc)
            self.stop_video()
            return None

    def stop_audio(self) -> None:
        """Immediately stop and release audio resources."""
        if self._audio_player:
            try:
                self._audio_player.stop()
                self._audio_player.setSource(QUrl())
            except Exception as exc:
                logger.debug("Audio stop notice: %s", exc)
            self._audio_player.deleteLater()
            self._audio_player = None

        if self._audio_output:
            self._audio_output.deleteLater()
            self._audio_output = None

    def stop_video(self) -> None:
        """Immediately stop and release video resources."""
        if self._video_player:
            try:
                self._video_player.stop()
                self._video_player.setSource(QUrl())
            except Exception as exc:
                logger.debug("Video stop notice: %s", exc)
            self._video_player.deleteLater()
            self._video_player = None

        if self._video_widget:
            self._video_widget.deleteLater()
            self._video_widget = None

    def stop_all(self) -> None:
        """Immediately stop both audio and video playback."""
        self.stop_audio()
        self.stop_video()
        logger.debug("All media playback stopped.")
