"""Unit tests for OS autostart manager."""

import os
from pathlib import Path
from startup.startup_manager import StartupManager


def test_startup_manager_linux_xdg(tmp_path: Path, monkeypatch):
    """Test XDG autostart file generation and removal on Linux."""
    # Set XDG_CONFIG_HOME to temporary path
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    mgr = StartupManager(executable_path="/usr/bin/noinsta")

    assert not mgr.is_autostart_enabled()

    # Enable
    assert mgr.enable_autostart()
    assert mgr.is_autostart_enabled()

    desktop_file = tmp_path / "autostart" / "noinsta.desktop"
    assert desktop_file.exists()

    content = desktop_file.read_text(encoding="utf-8")
    assert "Exec=/usr/bin/noinsta" in content
    assert "Type=Application" in content

    # Disable
    assert mgr.disable_autostart()
    assert not mgr.is_autostart_enabled()
    assert not desktop_file.exists()
