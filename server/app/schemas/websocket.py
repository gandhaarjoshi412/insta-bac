"""Pydantic schemas and protocol definitions for WebSocket communications."""

from enum import Enum
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict


class MessageType(str, Enum):
    AUTHENTICATE = "authenticate"
    AUTHENTICATED = "authenticated"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    INSTAGRAM_OPEN = "instagram_open"
    INTERVENTION_RECEIVED = "intervention_received"
    INTERVENTION_CLOSED = "intervention_closed"
    ERROR = "error"


class WSBaseMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str


# Client -> Server
class WSAuthMessage(WSBaseMessage):
    type: Literal["authenticate"] = "authenticate"
    access_token: str
    device_id: Optional[str] = None


class WSHeartbeatMessage(WSBaseMessage):
    type: Literal["heartbeat"] = "heartbeat"
    device_id: Optional[str] = None
    timestamp: Optional[str] = None


class WSInterventionReceivedMessage(WSBaseMessage):
    type: Literal["intervention_received"] = "intervention_received"
    event_id: str
    device_id: Optional[str] = None


class WSInterventionClosedMessage(WSBaseMessage):
    type: Literal["intervention_closed"] = "intervention_closed"
    event_id: str
    device_id: Optional[str] = None
    timestamp: Optional[str] = None


# Server -> Client
class WSAuthenticatedMessage(BaseModel):
    type: Literal["authenticated"] = "authenticated"
    device_id: str
    user_id: str


class WSHeartbeatAckMessage(BaseModel):
    type: Literal["heartbeat_ack"] = "heartbeat_ack"


class WSInstagramOpenMessage(BaseModel):
    type: Literal["instagram_open"] = "instagram_open"
    event_id: str
    timestamp: str


class WSErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    detail: str
