"""HTTPS API Client for NoInsta authentication, pairing, and token operations."""

import logging
import platform
import socket
from typing import Optional, Tuple

import httpx

from models.messages import DeviceCredentials, PairingRequest, PairingResponse

logger = logging.getLogger(__name__)


class APIEndpoints:
    """Centralized REST API routes for NoInsta server."""
    HEALTH = "/health"
    PAIR_DEVICE = "/api/v1/devices/pair"
    REFRESH_TOKEN = "/api/v1/auth/refresh"
    DEVICE_STATUS = "/api/v1/devices/{device_id}/status"


class APIClient:
    """Handles HTTPS requests to NoInsta server."""

    def __init__(self, base_url: str = "https://noinsta.platesight.in", timeout_seconds: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _get_client(self) -> httpx.Client:
        """Create an HTTP client with strict TLS certificate verification."""
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            verify=True,  # Never disable TLS verification
            headers={
                "User-Agent": f"NoInsta-Client/1.0 ({platform.system()} {platform.release()})",
                "Accept": "application/json",
            },
        )

    def check_health(self) -> bool:
        """Check if the NoInsta server is reachable and responsive."""
        try:
            with self._get_client() as client:
                resp = client.get(APIEndpoints.HEALTH)
                return resp.status_code < 400
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", self.base_url, exc)
            return False

    def pair_device(
        self, pairing_code: str, device_name: Optional[str] = None
    ) -> Tuple[bool, Optional[DeviceCredentials], str]:
        """Submit one-time pairing code to receive permanent device credentials.
        
        Returns: (success: bool, credentials: Optional[DeviceCredentials], message: str)
        """
        clean_code = pairing_code.strip()
        if not clean_code:
            return False, None, "Pairing code cannot be empty."

        name = device_name.strip() if device_name else socket.gethostname()
        plat_info = f"{platform.system()} {platform.release()}"

        req = PairingRequest(
            pairing_code=clean_code,
            device_name=name,
            platform=plat_info,
        )

        logger.info("Initiating device pairing with server: %s", self.base_url)

        try:
            with self._get_client() as client:
                resp = client.post(
                    APIEndpoints.PAIR_DEVICE,
                    json=req.model_dump(),
                )

                if resp.status_code == 200 or resp.status_code == 201:
                    data = resp.json()
                    pair_resp = PairingResponse.model_validate(data)
                    
                    credentials = DeviceCredentials(
                        device_id=pair_resp.device_id,
                        access_token=pair_resp.access_token,
                        refresh_token=pair_resp.refresh_token,
                        user_id=pair_resp.user_id,
                        device_name=name,
                        server_url=self.base_url,
                    )
                    logger.info("Device successfully paired. Device ID: %s", credentials.device_id)
                    return True, credentials, "Device paired successfully."

                elif resp.status_code == 400 or resp.status_code == 404:
                    err_msg = "Invalid or expired pairing code."
                    try:
                        err_detail = resp.json().get("detail")
                        if err_detail:
                            err_msg = str(err_detail)
                    except Exception:
                        pass
                    logger.warning("Pairing failed (HTTP %d): %s", resp.status_code, err_msg)
                    return False, None, err_msg

                else:
                    logger.warning("Pairing failed with HTTP status %d", resp.status_code)
                    return False, None, f"Server error ({resp.status_code}). Please try again."

        except httpx.ConnectError:
            msg = "Could not connect to NoInsta server. Check network connection."
            logger.error("Connection error during pairing: %s", msg)
            return False, None, msg
        except httpx.TimeoutException:
            msg = "Connection timed out while contacting server."
            logger.error("Timeout during pairing: %s", msg)
            return False, None, msg
        except Exception as exc:
            msg = f"Unexpected error during pairing: {exc}"
            logger.error("Error pairing device: %s", exc)
            return False, None, msg

    def refresh_access_token(
        self, device_id: str, refresh_token: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Request new access token using refresh token.
        
        Returns: (success: bool, new_access_token: Optional[str], new_refresh_token: Optional[str])
        """
        if not refresh_token:
            return False, None, None

        try:
            with self._get_client() as client:
                resp = client.post(
                    APIEndpoints.REFRESH_TOKEN,
                    json={"device_id": device_id, "refresh_token": refresh_token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    new_access = data.get("access_token")
                    new_refresh = data.get("refresh_token") or refresh_token
                    logger.info("Access token successfully refreshed for device '%s'", device_id)
                    return True, new_access, new_refresh
                else:
                    logger.warning("Token refresh rejected (HTTP %d)", resp.status_code)
                    return False, None, None
        except Exception as exc:
            logger.error("Error while refreshing token: %s", exc)
            return False, None, None
