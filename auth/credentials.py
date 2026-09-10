"""Credential manager providing high-level authentication credentials management."""

import json
import logging
from typing import Optional

from auth.storage import CredentialStorage
from models.messages import DeviceCredentials

logger = logging.getLogger(__name__)


class CredentialManager:
    """Manages the lifecycle of device authentication credentials."""

    def __init__(self, storage: Optional[CredentialStorage] = None):
        self.storage = storage or CredentialStorage()
        self._cached_credentials: Optional[DeviceCredentials] = None

    def is_paired(self) -> bool:
        """Check whether valid device credentials are currently stored."""
        return self.get_credentials() is not None

    def get_credentials(self) -> Optional[DeviceCredentials]:
        """Load and return current device credentials, if available."""
        if self._cached_credentials is not None:
            return self._cached_credentials

        raw = self.storage.retrieve_raw()
        if not raw:
            return None

        try:
            creds = DeviceCredentials.model_validate_json(raw)
            self._cached_credentials = creds
            logger.info("Loaded credentials for device '%s'", creds.device_id)
            return creds
        except Exception as exc:
            logger.warning("Failed to deserialize stored credentials: %s", exc)
            return None

    def save_credentials(self, credentials: DeviceCredentials) -> bool:
        """Persist device credentials."""
        try:
            raw_json = credentials.model_dump_json()
            if self.storage.store_raw(raw_json):
                self._cached_credentials = credentials
                logger.info("Credentials successfully saved for device '%s'", credentials.device_id)
                return True
            return False
        except Exception as exc:
            logger.error("Error serializing credentials: %s", exc)
            return False

    def clear_credentials(self) -> bool:
        """Remove credentials upon user unpairing or authentication reset."""
        self._cached_credentials = None
        return self.storage.delete_raw()

    def update_tokens(self, access_token: str, refresh_token: Optional[str] = None) -> bool:
        """Update existing credentials with fresh tokens."""
        creds = self.get_credentials()
        if not creds:
            logger.warning("Cannot update tokens: No existing credentials found.")
            return False

        updated = creds.model_copy(
            update={
                "access_token": access_token,
                "refresh_token": refresh_token or creds.refresh_token,
            }
        )
        return self.save_credentials(updated)
