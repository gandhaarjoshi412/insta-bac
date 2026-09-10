"""Per-user OS autostart management for Windows and Fedora Linux (X11 & Wayland)."""

import logging
import os
import platform
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

APP_NAME = "NoInsta"
DESKTOP_FILENAME = "noinsta.desktop"


class StartupManager:
    """Configures automatic application startup at user login without root privileges."""

    def __init__(self, executable_path: Optional[str] = None):
        if executable_path:
            self.exec_cmd = executable_path
        else:
            # Default to running current python interpreter with main.py
            main_script = Path(__file__).resolve().parent.parent / "main.py"
            self.exec_cmd = f'"{sys.executable}" "{main_script}"'

    def is_autostart_enabled(self) -> bool:
        """Check whether autostart is currently enabled for this user."""
        system = platform.system()
        if system == "Windows":
            return self._is_windows_autostart_enabled()
        elif system == "Linux":
            return self._is_linux_autostart_enabled()
        return False

    def enable_autostart(self) -> bool:
        """Register application to start automatically on user login."""
        system = platform.system()
        if system == "Windows":
            return self._enable_windows_autostart()
        elif system == "Linux":
            return self._enable_linux_autostart()
        else:
            logger.warning("Autostart not supported on platform: %s", system)
            return False

    def disable_autostart(self) -> bool:
        """Remove application from automatic startup."""
        system = platform.system()
        if system == "Windows":
            return self._disable_windows_autostart()
        elif system == "Linux":
            return self._disable_linux_autostart()
        else:
            logger.warning("Autostart not supported on platform: %s", system)
            return False

    # -----------------------------------------------------------------------
    # Linux (Fedora X11 and Wayland standard XDG autostart)
    # -----------------------------------------------------------------------

    def _get_linux_autostart_file(self) -> Path:
        """Return path to ~/.config/autostart/noinsta.desktop."""
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            autostart_dir = Path(xdg_config) / "autostart"
        else:
            autostart_dir = Path.home() / ".config" / "autostart"
        autostart_dir.mkdir(parents=True, exist_ok=True)
        return autostart_dir / DESKTOP_FILENAME

    def _is_linux_autostart_enabled(self) -> bool:
        return self._get_linux_autostart_file().exists()

    def _enable_linux_autostart(self) -> bool:
        desktop_file = self._get_linux_autostart_file()
        content = f"""[Desktop Entry]
Type=Application
Version=1.0
Name=NoInsta
Comment=NoInsta Productivity Control Client
Exec={self.exec_cmd}
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
StartupNotify=false
"""
        try:
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(content)
            # Ensure proper permissions
            desktop_file.chmod(0o755)
            logger.info("Enabled Linux XDG autostart at %s", desktop_file)
            return True
        except Exception as exc:
            logger.error("Failed to enable Linux autostart: %s", exc)
            return False

    def _disable_linux_autostart(self) -> bool:
        desktop_file = self._get_linux_autostart_file()
        if desktop_file.exists():
            try:
                desktop_file.unlink()
                logger.info("Disabled Linux autostart (%s removed)", desktop_file)
                return True
            except Exception as exc:
                logger.error("Failed to remove Linux autostart file: %s", exc)
                return False
        return True

    # -----------------------------------------------------------------------
    # Windows (Registry Run Key)
    # -----------------------------------------------------------------------

    def _is_windows_autostart_enabled(self) -> bool:
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            )
            try:
                value, _ = winreg.QueryValueEx(key, APP_NAME)
                return bool(value)
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception as exc:
            logger.debug("Windows registry check notice: %s", exc)
            return False

    def _enable_windows_autostart(self) -> bool:
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, self.exec_cmd)
                logger.info("Registered NoInsta in Windows HKCU Run key.")
                return True
            finally:
                winreg.CloseKey(key)
        except Exception as exc:
            logger.error("Failed to enable Windows autostart: %s", exc)
            return False

    def _disable_windows_autostart(self) -> bool:
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, APP_NAME)
                logger.info("Removed NoInsta from Windows HKCU Run key.")
                return True
            except FileNotFoundError:
                return True
            finally:
                winreg.CloseKey(key)
        except Exception as exc:
            logger.error("Failed to disable Windows autostart: %s", exc)
            return False
