"""Configuration data models for NoInsta client."""

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class MediaConfig(BaseModel):
    """Configuration for intervention media assets."""
    image_path: Optional[str] = "assets/alert.png"
    video_path: Optional[str] = None
    audio_path: Optional[str] = "assets/alert.wav"
    loop_video: bool = True
    loop_audio: bool = True


class WindowConfig(BaseModel):
    """Configuration for intervention window display."""
    always_on_top: bool = True
    title: str = "NoInsta"
    headline: str = "NO INSTAGRAM"
    subheading: str = "STOP SCROLLING. GET BACK TO WORK."
    button_text: str = "CLOSE INTERVENTION"
    width: int = 520
    height: int = 500


class AppConfig(BaseModel):
    """Root application configuration."""
    server_url: str = "https://noinsta.platesight.in"
    ws_url: Optional[str] = None
    heartbeat_interval_seconds: int = Field(default=120, ge=10, le=3600)
    reconnect_max_delay_seconds: int = Field(default=60, ge=5, le=300)
    dedup_window_seconds: int = Field(default=600, ge=60)
    log_level: str = "INFO"
    media: MediaConfig = Field(default_factory=MediaConfig)
    window: WindowConfig = Field(default_factory=WindowConfig)

    def get_effective_ws_url(self, device_id: Optional[str] = None) -> str:
        """Derive standard WebSocket URL from server_url or explicit override."""
        if self.ws_url:
            return self.ws_url
        
        base = self.server_url.strip()
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://"):]
        else:
            ws_base = "wss://" + base
        
        ws_base = ws_base.rstrip("/")
        if device_id:
            return f"{ws_base}/ws/device/{device_id}"
        return f"{ws_base}/ws/device"
