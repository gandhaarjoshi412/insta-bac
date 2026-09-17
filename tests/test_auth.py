"""Unit tests for credential storage and lifecycle management."""

import os
import stat
from pathlib import Path
import pytest

from auth.credentials import CredentialManager
from auth.storage import CredentialStorage
from models.messages import DeviceCredentials


class MockInMemoryStorage(CredentialStorage):
    """Storage mock for isolated testing."""

    def __init__(self, tmp_path: Path):
        self.service_name = "test_noinsta"
        self.fallback_path = tmp_path / ".test_credentials"
        self._keyring_functional = False  # Test file fallback path
        self._data = None

    def store_raw(self, raw_json: str) -> bool:
        # Write to fallback file to verify file permissions
        super().store_raw(raw_json)
        self._data = raw_json
        return True

    def retrieve_raw(self):
        if self.fallback_path.exists():
            return super().retrieve_raw()
        return self._data

    def delete_raw(self) -> bool:
        self._data = None
        return super().delete_raw()


def test_credential_storage_lifecycle(tmp_path: Path):
    storage = MockInMemoryStorage(tmp_path)
    manager = CredentialManager(storage=storage)

    assert not manager.is_paired()
    assert manager.get_credentials() is None

    creds = DeviceCredentials(
        device_id="laptop_test_42",
        access_token="tok_abc123",
        refresh_token="ref_xyz789",
        user_id="user_101",
        device_name="Gandhaar Laptop",
        server_url="https://noinsta.platesight.in",
        paired_at="2026-09-17T00:00:00Z",
    )

    assert manager.save_credentials(creds)
    assert manager.is_paired()

    loaded = manager.get_credentials()
    assert loaded is not None
    assert loaded.device_id == "laptop_test_42"
    assert loaded.access_token == "tok_abc123"
    assert loaded.refresh_token == "ref_xyz789"
    assert loaded.device_name == "Gandhaar Laptop"

    # Verify fallback file permission on Linux/Unix (0600)
    if os.name != "nt":
        file_stat = storage.fallback_path.stat()
        file_mode = stat.S_IMODE(file_stat.st_mode)
        assert file_mode == 0o600

    # Test token update
    assert manager.update_tokens("new_access_token", "new_refresh_token")
    updated = manager.get_credentials()
    assert updated.access_token == "new_access_token"
    assert updated.refresh_token == "new_refresh_token"

    # Test clear credentials
    assert manager.clear_credentials()
    assert not manager.is_paired()
    assert manager.get_credentials() is None
    assert not storage.fallback_path.exists()
