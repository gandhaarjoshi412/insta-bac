"""Application configuration and path resolution for NoInsta client."""

import json
import logging
import os
import platform
import sys
from pathlib import Path
from typing import Optional

from models.config_models import AppConfig, MediaConfig, WindowConfig

logger = logging.getLogger(__name__)

APP_NAME = "NoInsta"


def get_base_dir() -> Path:
    """Return the base directory where the application code resides."""
    return Path(__file__).resolve().parent


def get_app_dir() -> Path:
    """Return the platform-appropriate per-user configuration/data directory.
    
    Windows: %APPDATA%\\NoInsta
    Linux/Unix: $XDG_CONFIG_HOME/noinsta or ~/.config/noinsta
    """
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = Path(appdata) / APP_NAME
        else:
            path = Path.home() / "AppData" / "Roaming" / APP_NAME
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            path = Path(xdg_config) / APP_NAME.lower()
        else:
            path = Path.home() / ".config" / APP_NAME.lower()

    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_file_path() -> Path:
    """Return the full path to config.json."""
    return get_app_dir() / "config.json"


def load_config() -> AppConfig:
    """Load configuration from config.json or return defaults and create template."""
    config_file = get_config_file_path()
    if not config_file.exists():
        default_config = AppConfig()
        save_config(default_config)
        logger.info("Initialized default configuration at %s", config_file)
        return default_config

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        config = AppConfig.model_validate(data)
        logger.info("Loaded configuration from %s", config_file)
        return config
    except Exception as exc:
        logger.warning(
            "Failed to load configuration from %s (%s). Falling back to defaults.",
            config_file,
            exc,
        )
        return AppConfig()


def save_config(config: AppConfig) -> None:
    """Persist configuration to config.json."""
    config_file = get_config_file_path()
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config.model_dump_json(indent=2))
        logger.info("Saved configuration to %s", config_file)
    except Exception as exc:
        logger.error("Failed to save configuration to %s: %s", config_file, exc)


def resolve_asset_path(raw_path: Optional[str]) -> Optional[Path]:
    """Resolve an asset path against config directory or base app directory.
    
    Returns Path if found, otherwise None.
    """
    if not raw_path:
        return None

    path = Path(raw_path)
    # If absolute and exists
    if path.is_absolute() and path.exists():
        return path

    # Check relative to app directory (e.g. ~/.config/noinsta/assets/...)
    config_rel = get_app_dir() / path
    if config_rel.exists():
        return config_rel

    # Check relative to code repository root
    base_rel = get_base_dir() / path
    if base_rel.exists():
        return base_rel

    logger.warning("Configured asset path does not exist: %s", raw_path)
    return None


def setup_logging(log_level: str = "INFO") -> None:
    """Initialize structured application logging with file and console handlers."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    log_file = get_app_dir() / "noinsta.log"

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-7s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Avoid duplicate handlers on re-init
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Suppress verbose third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.INFO)

    logger.info("Logging configured at level %s (log file: %s)", log_level, log_file)
