"""Unit tests for InterventionWindow and MediaManager."""

from pathlib import Path
from models.config_models import AppConfig, MediaConfig, WindowConfig
from ui.intervention_window import InterventionWindow
from ui.media_player import MediaManager


def test_media_manager_missing_files(qapp):
    manager = MediaManager()
    # Missing audio should safely return False
    assert not manager.play_audio(Path("/non/existent/audio.wav"))
    # Missing video should safely return None
    assert manager.setup_video(Path("/non/existent/video.mp4")) is None
    # Stop all should be safe even when nothing was playing
    manager.stop_all()


def test_media_manager_with_valid_asset(qapp):
    alert_wav = Path("assets/alert.wav")
    if alert_wav.exists():
        manager = MediaManager()
        started = manager.play_audio(alert_wav, loop=False)
        assert started is True
        manager.stop_all()


def test_intervention_window_lifecycle(qapp):
    closed_events = []

    def on_closed(eid: str):
        closed_events.append(eid)

    config = AppConfig(
        media=MediaConfig(
            image_path="assets/alert.png",
            video_path=None,
            audio_path="assets/alert.wav",
        ),
        window=WindowConfig(always_on_top=False),
    )

    window = InterventionWindow(
        event_id="test_evt_unit_1",
        config=config,
        on_closed_callback=on_closed,
    )

    assert window.event_id == "test_evt_unit_1"
    assert window.windowTitle() == config.window.title

    # Dismiss window
    window.dismiss()

    assert "test_evt_unit_1" in closed_events
    assert window._is_dismissed is True


def test_intervention_window_missing_media_fallback(qapp):
    closed_events = []

    config = AppConfig(
        media=MediaConfig(
            image_path="/invalid/path.png",
            video_path=None,
            audio_path="/invalid/sound.wav",
        ),
        window=WindowConfig(always_on_top=False),
    )

    window = InterventionWindow(
        event_id="test_fallback_evt",
        config=config,
        on_closed_callback=lambda eid: closed_events.append(eid),
    )

    assert window.isVisible() is False
    window.dismiss()
    assert "test_fallback_evt" in closed_events
