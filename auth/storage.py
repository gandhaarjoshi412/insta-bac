"""Secure credential storage implementation using OS keyring with isolated fallback."""

import json
import logging
import os
import platform
from pathlib import Path
from typing import Optional

try:
    import keyring
    import keyring.errors
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

from config import get_app_dir

logger = logging.getLogger(__name__)

SERVICE_NAME = "noinsta_client"
CREDENTIAL_KEY = "device_credentials"
FALLBACK_FILENAME = ".device_credentials"


class CredentialStorage:
    """Handles secure persistence of device credentials.
    
    Primary storage: OS keyring (Windows Credential Manager / Linux Secret Service).
    Fallback storage: POSIX chmod 0600 user-restricted file in the app directory.
    """

    def __init__(self, service_name: str = SERVICE_NAME):
        self.service_name = service_name
        self.fallback_path: Path = get_app_dir() / FALLBACK_FILENAME
        self._keyring_functional = self._test_keyring()

    def _test_keyring(self) -> bool:
        """Verify if the OS keyring is functional in this environment."""
        if not KEYRING_AVAILABLE:
            logger.info("Keyring module not available. Using isolated secure file fallback.")
            return False

        try:
            backend = keyring.get_keyring()
            backend_name = backend.__class__.__name__
            # Check for dummy or fail backends
            if "fail" in backend_name.lower() or "dummy" in backend_name.lower() or "null" in backend_name.lower():
                logger.warning(
                    "Keyring backend '%s' is not persistent. Falling back to local secure storage.",
                    backend_name,
                )
                return False
            return True
        except Exception as exc:
            logger.warning("Keyring initialization check failed (%s). Using fallback storage.", exc)
            return False

    def store_raw(self, raw_json: str) -> bool:
        """Store serialized credential JSON into keyring or secure fallback."""
        if self._keyring_functional:
            try:
                keyring.set_password(self.service_name, CREDENTIAL_KEY, raw_json)
                logger.info("Stored credentials in OS keyring (%s)", self.service_name)
                # Clean up fallback if it existed
                if self.fallback_path.exists():
                    try:
                        self.fallback_path.unlink()
                    except OSError:
                        pass
                return True
            except Exception as exc:
                logger.warning(
                    "Failed to save credentials to OS keyring (%s). Trying fallback storage.",
                    exc,
                )

        # Fallback to local user-restricted file
        try:
            # Create file with 0600 permissions
            if platform.system() != "Windows":
                # Create with restricted permissions before writing
                fd = os.open(
                    self.fallback_path,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    0o600,
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(raw_json)
            else:
                with open(self.fallback_path, "w", encoding="utf-8") as f:
                    f.write(raw_json)

            logger.info("Stored credentials in secure fallback file at %s", self.fallback_path)
            return True
        except Exception as exc:
            logger.error("Failed to store credentials in fallback storage: %s", exc)
            return False

    def retrieve_raw(self) -> Optional[str]:
        """Retrieve serialized credential JSON from keyring or fallback file."""
        if self._keyring_functional:
            try:
                raw_json = keyring.get_password(self.service_name, CREDENTIAL_KEY)
                if raw_json:
                    return raw_json
            except Exception as exc:
                logger.warning("Failed to retrieve credentials from OS keyring: %s", exc)

        # Try fallback file if keyring returned None or failed
        if self.fallback_path.exists():
            try:
                with open(self.fallback_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as exc:
                logger.error("Failed to read credentials from fallback file: %s", exc)

        return None

    def delete_raw(self) -> bool:
        """Delete credentials from keyring and fallback storage."""
        success = True
        if self._keyring_functional:
            try:
                keyring.delete_password(self.service_name, CREDENTIAL_KEY)
                logger.info("Removed credentials from OS keyring")
            except Exception as exc:
                # Keyring might raise PasswordDeleteError if not found
                logger.debug("Keyring delete notice: %s", exc)

        if self.fallback_path.exists():
            try:
                self.fallback_path.unlink()
                logger.info("Removed fallback credentials file")
            except Exception as exc:
                logger.error("Failed to delete fallback credentials file: %s", exc)
                success = False

        return success
