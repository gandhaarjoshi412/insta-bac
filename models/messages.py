"""Protocol message definitions and models for NoInsta client."""

from datetime import datetime, timezone
from enum import Enum
import json
import logging
from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


def current_utc_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class ConnectionState(str, Enum):
    """Explicit connection and application states."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATING = "AUTHENTICATING"
    CONNECTED = "CONNECTED"
    INTERVENTION_ACTIVE = "INTERVENTION_ACTIVE"


# ---------------------------------------------------------------------------
# Inbound Server Messages (Server -> Laptop)
# ---------------------------------------------------------------------------

class InboundMessageType(str, Enum):
    INSTAGRAM_OPEN = "instagram_open"
    PING = "ping"
    HEARTBEAT_ACK = "heartbeat_ack"
    AUTH_ERROR = "auth_error"
    ERROR = "error"
    AUTHENTICATED = "authenticated"
    UNKNOWN = "unknown"


class BaseInboundMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    timestamp: Optional[str] = None


class InstagramOpenMessage(BaseInboundMessage):
    """Server notification indicating Instagram was opened on the phone."""
    type: Literal["instagram_open"] = "instagram_open"
    event_id: str
    metadata: Optional[Dict[str, Any]] = None


class PingMessage(BaseInboundMessage):
    """Keepalive ping from server."""
    type: Literal["ping"] = "ping"


class HeartbeatAckMessage(BaseInboundMessage):
    """Acknowledgment of client heartbeat."""
    type: Literal["heartbeat_ack"] = "heartbeat_ack"


class AuthErrorMessage(BaseInboundMessage):
    """Notification of authentication or authorization error."""
    type: Literal["auth_error"] = "auth_error"
    reason: Optional[str] = None


class ErrorMessage(BaseInboundMessage):
    """Notification of server error or auth failure."""
    type: Literal["error"] = "error"
    detail: Optional[str] = None
    reason: Optional[str] = None


class AuthenticatedMessage(BaseInboundMessage):
    """Notification of successful server authentication."""
    type: Literal["authenticated"] = "authenticated"
    detail: Optional[str] = None


def parse_inbound_message(raw_data: Union[str, bytes]) -> Optional[BaseInboundMessage]:
    """Parse incoming WebSocket text payload into a validated message object.
    
    Returns None safely on malformed JSON or unrecognized messages.
    Never raises exceptions.
    """
    try:
        if isinstance(raw_data, bytes):
            raw_text = raw_data.decode("utf-8")
        else:
            raw_text = raw_data
        
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            logger.warning("Incoming message is not a JSON object: %s", type(data))
            return None
        
        msg_type = data.get("type")
        if not msg_type:
            logger.warning("Incoming message missing 'type' field: %s", data)
            return None
        
        if msg_type == InboundMessageType.INSTAGRAM_OPEN:
            return InstagramOpenMessage.model_validate(data)
        elif msg_type == InboundMessageType.PING:
            return PingMessage.model_validate(data)
        elif msg_type == InboundMessageType.HEARTBEAT_ACK:
            return HeartbeatAckMessage.model_validate(data)
        elif msg_type == InboundMessageType.AUTH_ERROR:
            return AuthErrorMessage.model_validate(data)
        elif msg_type == InboundMessageType.ERROR:
            return ErrorMessage.model_validate(data)
        elif msg_type == InboundMessageType.AUTHENTICATED:
            return AuthenticatedMessage.model_validate(data)
        else:
            # Safe forward-compatible warning without crashing
            logger.warning("Unknown or unsupported server message type: %s", msg_type)
            return None
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse incoming WebSocket message as JSON: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Validation error while parsing incoming message: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Outbound Client Messages (Laptop -> Server)
# ---------------------------------------------------------------------------

class OutboundMessageType(str, Enum):
    AUTHENTICATE = "authenticate"
    HEARTBEAT = "heartbeat"
    INTERVENTION_CLOSED = "intervention_closed"
    INTERVENTION_RECEIVED = "intervention_received"


class BaseOutboundMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    timestamp: str = Field(default_factory=current_utc_iso)


class AuthenticateMessage(BaseOutboundMessage):
    """Handshake payload sent over WebSocket upon connection."""
    type: Literal["authenticate"] = "authenticate"
    device_id: str
    access_token: str

    def __repr__(self) -> str:
        return f"AuthenticateMessage(device_id={self.device_id!r}, access_token='***', timestamp={self.timestamp!r})"


class HeartbeatMessage(BaseOutboundMessage):
    """Periodic health beacon indicating laptop client is alive."""
    type: Literal["heartbeat"] = "heartbeat"
    device_id: str


class InterventionClosedMessage(BaseOutboundMessage):
    """Sent when user presses the intervention stop/close button."""
    type: Literal["intervention_closed"] = "intervention_closed"
    event_id: str
    device_id: str


class InterventionReceivedMessage(BaseOutboundMessage):
    """Sent immediately when intervention window is displayed."""
    type: Literal["intervention_received"] = "intervention_received"
    event_id: str
    device_id: str


# ---------------------------------------------------------------------------
# Pairing & Credentials Models
# ---------------------------------------------------------------------------

class PairingRequest(BaseModel):
    pairing_code: str
    device_name: str
    platform: str


class PairingResponse(BaseModel):
    device_id: str
    access_token: str
    refresh_token: Optional[str] = None
    user_id: Optional[str] = None
    message: Optional[str] = None


class PairingGenerateRequest(BaseModel):
    device_name: Optional[str] = None
    platform: Optional[str] = None
    device_type: Optional[str] = "LAPTOP"


class PairingGenerateResponse(BaseModel):
    pairing_code: str
    expires_at: str
    expires_in_seconds: int
    device_id: str
    access_token: str
    refresh_token: str
    user_id: str
    message: Optional[str] = None


class PairingStatusCheckResponse(BaseModel):
    pairing_code: str
    is_claimed: bool
    claimed_device_name: Optional[str] = None
    expires_at: Optional[str] = None
    is_expired: bool = False
    message: Optional[str] = None



class DeviceCredentials(BaseModel):
    """Device identity and authorization tokens."""
    device_id: str
    access_token: str
    refresh_token: Optional[str] = None
    user_id: Optional[str] = None
    device_name: Optional[str] = None
    server_url: Optional[str] = None
    paired_at: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"DeviceCredentials(device_id={self.device_id!r}, "
            f"user_id={self.user_id!r}, "
            f"access_token='***', "
            f"has_refresh_token={bool(self.refresh_token)}, "
            f"server_url={self.server_url!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()
