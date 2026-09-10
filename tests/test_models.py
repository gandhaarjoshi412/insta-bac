"""Unit tests for protocol message models, validation, and configuration."""

import json
from models.config_models import AppConfig, MediaConfig, WindowConfig
from models.messages import (
    AuthenticateMessage,
    AuthErrorMessage,
    ConnectionState,
    DeviceCredentials,
    HeartbeatAckMessage,
    HeartbeatMessage,
    InboundMessageType,
    InstagramOpenMessage,
    InterventionClosedMessage,
    InterventionReceivedMessage,
    PingMessage,
    parse_inbound_message,
)


def test_parse_instagram_open_message():
    raw = json.dumps({
        "type": "instagram_open",
        "event_id": "evt_abc123",
        "timestamp": "2026-09-10T12:00:00Z",
        "metadata": {"app_version": "1.0"},
    })
    msg = parse_inbound_message(raw)
    assert isinstance(msg, InstagramOpenMessage)
    assert msg.type == "instagram_open"
    assert msg.event_id == "evt_abc123"
    assert msg.timestamp == "2026-09-10T12:00:00Z"
    assert msg.metadata == {"app_version": "1.0"}


def test_parse_ping_and_ack_messages():
    ping_msg = parse_inbound_message('{"type": "ping"}')
    assert isinstance(ping_msg, PingMessage)

    ack_msg = parse_inbound_message('{"type": "heartbeat_ack"}')
    assert isinstance(ack_msg, HeartbeatAckMessage)


def test_parse_auth_error_message():
    msg = parse_inbound_message('{"type": "auth_error", "reason": "token_expired"}')
    assert isinstance(msg, AuthErrorMessage)
    assert msg.reason == "token_expired"


def test_parse_malformed_and_unknown_messages():
    # Malformed JSON
    assert parse_inbound_message("invalid json content") is None

    # Not a JSON object (array or string)
    assert parse_inbound_message("[]") is None
    assert parse_inbound_message('"just a string"') is None

    # Missing type
    assert parse_inbound_message('{"event_id": "123"}') is None

    # Unknown type
    assert parse_inbound_message('{"type": "non_existent_command"}') is None

    # Missing required field for instagram_open (missing event_id)
    assert parse_inbound_message('{"type": "instagram_open"}') is None


def test_outbound_messages_serialization():
    # Authenticate
    auth = AuthenticateMessage(device_id="dev_1", access_token="secret_token")
    auth_data = json.loads(auth.model_dump_json())
    assert auth_data["type"] == "authenticate"
    assert auth_data["device_id"] == "dev_1"
    assert auth_data["access_token"] == "secret_token"
    # Ensure repr hides the secret
    assert "secret_token" not in repr(auth)

    # Heartbeat
    hb = HeartbeatMessage(device_id="dev_1")
    hb_data = json.loads(hb.model_dump_json())
    assert hb_data["type"] == "heartbeat"
    assert hb_data["device_id"] == "dev_1"
    assert "timestamp" in hb_data

    # Intervention closed
    close_msg = InterventionClosedMessage(event_id="evt_99", device_id="dev_1")
    close_data = json.loads(close_msg.model_dump_json())
    assert close_data["type"] == "intervention_closed"
    assert close_data["event_id"] == "evt_99"

    # Intervention received
    recv_msg = InterventionReceivedMessage(event_id="evt_99", device_id="dev_1")
    recv_data = json.loads(recv_msg.model_dump_json())
    assert recv_data["type"] == "intervention_received"


def test_device_credentials_secret_masking():
    creds = DeviceCredentials(
        device_id="dev_123",
        access_token="super_secret_access_token_jwt",
        refresh_token="super_secret_refresh_token",
        user_id="usr_456",
        server_url="https://noinsta.platesight.in",
    )

    repr_str = repr(creds)
    assert "super_secret_access_token_jwt" not in repr_str
    assert "super_secret_refresh_token" not in repr_str
    assert "dev_123" in repr_str
    assert "usr_456" in repr_str

    str_repr = str(creds)
    assert "super_secret_access_token_jwt" not in str_repr


def test_app_config_ws_url_derivation():
    config = AppConfig(server_url="https://noinsta.platesight.in")
    assert config.get_effective_ws_url("dev_1") == "wss://noinsta.platesight.in/ws/device/dev_1"

    # With custom explicit ws_url
    config_custom = AppConfig(
        server_url="https://noinsta.platesight.in",
        ws_url="wss://custom.domain/ws",
    )
    assert config_custom.get_effective_ws_url("dev_1") == "wss://custom.domain/ws"
