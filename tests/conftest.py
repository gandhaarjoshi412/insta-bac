"""Pytest test configuration and fixtures."""

import os
import sys
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QGuiApplication / QApplication instance exists for tests."""
    app = QApplication.instance()
    if app is None:
        # Offscreen platform for headless test execution
        app = QApplication(["-platform", "offscreen"])
    yield app
