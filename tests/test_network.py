"""Unit and integration tests for networking, deduplication, and WebSocket client."""

import asyncio
import json
import time
from typing import Optional
import httpx
import pytest

from models.config_models import AppConfig
from models.messages import (
    AuthenticateMessage,
    DeviceCredentials,
    HeartbeatMessage,
    InstagramOpenMessage,
    InterventionClosedMessage,
    InterventionReceivedMessage,
)
from network.api_client import APIClient, APIEndpoints
from network.heartbeat import HeartbeatManager
from network.websocket_client import EventDeduplicator, WebSocketClient


def test_event_deduplicator():
    dedup = EventDeduplicator(window_seconds=2)
    assert not dedup.is_duplicate("evt_1")
    assert dedup.is_duplicate("evt_1")
    assert not dedup.is_duplicate("evt_2")

    # Fast forward expiration
    time.sleep(2.1)
    assert not dedup.is_duplicate("evt_1")


def test_api_client_pairing_success():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == APIEndpoints.PAIR_DEVICE:
            return httpx.Response(
                status_code=200,
                json={
                    "device_id": "dev_test_99",
                    "access_token": "mock_access_token",
                    "refresh_token": "mock_refresh_token",
                    "user_id": "usr_test",
                },
            )
        return httpx.Response(status_code=404)

    client = APIClient(base_url="https://test.noinsta.internal")
    client._get_client = lambda: httpx.Client(
        transport=httpx.MockTransport(mock_handler),
        base_url=client.base_url,
    )

    success, creds, msg = client.pair_device("A7K9Q2", "TestLaptop")
    assert success is True
    assert creds is not None
    assert creds.device_id == "dev_test_99"
    assert creds.access_token == "mock_access_token"
    assert creds.refresh_token == "mock_refresh_token"


def test_api_client_pairing_invalid_code():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=400, json={"detail": "Expired pairing code"})

    client = APIClient(base_url="https://test.noinsta.internal")
    client._get_client = lambda: httpx.Client(
        transport=httpx.MockTransport(mock_handler),
        base_url=client.base_url,
    )

    success, creds, msg = client.pair_device("BADCODE", "TestLaptop")
    assert success is False
    assert creds is None
    assert "Expired pairing code" in msg


def test_api_client_token_refresh():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == APIEndpoints.REFRESH_TOKEN:
            return httpx.Response(
                status_code=200,
                json={"access_token": "new_tok_123", "refresh_token": "new_ref_456"},
            )
        return httpx.Response(status_code=400)

    client = APIClient(base_url="https://test.noinsta.internal")
    client._get_client = lambda: httpx.Client(
        transport=httpx.MockTransport(mock_handler),
        base_url=client.base_url,
    )

    success, new_access, new_refresh = client.refresh_access_token("dev_1", "old_ref")
    assert success is True
    assert new_access == "new_tok_123"
    assert new_refresh == "new_ref_456"


@pytest.mark.asyncio
async def test_heartbeat_manager_periodic_dispatch():
    dispatched_heartbeats = []

    def fake_send(hb: HeartbeatMessage):
        dispatched_heartbeats.append(hb)

    creds = DeviceCredentials(device_id="dev_hb", access_token="tok")
    manager = HeartbeatManager(
        interval_seconds=1,
        credentials_provider=lambda: creds,
        send_callback=fake_send,
    )

    manager.start()
    await asyncio.sleep(1.2)
    manager.stop()

    assert len(dispatched_heartbeats) >= 1
    assert dispatched_heartbeats[0].device_id == "dev_hb"
    assert dispatched_heartbeats[0].type == "heartbeat"


@pytest.mark.asyncio
async def test_websocket_client_communication():
    """Run an isolated in-process mock WebSocket server and test client behavior."""
    import websockets

    received_by_server = []
    server_ready = asyncio.Event()

    async def mock_ws_server(websocket):
        server_ready.set()
        async for msg in websocket:
            data = json.loads(msg)
            received_by_server.append(data)
            # When client authenticates, push an instagram_open event
            if data.get("type") == "authenticate":
                await websocket.send(json.dumps({
                    "type": "instagram_open",
                    "event_id": "test_evt_456",
                    "timestamp": "2026-09-10T12:00:00Z"
                }))

    # Start local mock WebSocket server on random port
    server = await websockets.serve(mock_ws_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    ws_url = f"ws://127.0.0.1:{port}/ws"

    triggered_events = []
    connection_states = []

    def on_instagram_open(event_id: str, ts: str):
        triggered_events.append(event_id)

    def on_connection_change(is_conn: bool):
        connection_states.append(is_conn)

    config = AppConfig(ws_url=ws_url, dedup_window_seconds=60)
    creds = DeviceCredentials(device_id="dev_ws_test", access_token="tok_secret")

    client = WebSocketClient(
        config=config,
        credentials_provider=lambda: creds,
        on_instagram_open=on_instagram_open,
        on_auth_error=lambda err: None,
        on_connection_change=on_connection_change,
    )

    client_task = asyncio.create_task(client.start())

    # Wait for server to receive authentication and send event
    for _ in range(30):
        if len(triggered_events) > 0 and len(received_by_server) >= 2:
            break
        await asyncio.sleep(0.1)

    assert "test_evt_456" in triggered_events

    # Now close intervention from client
    client.queue_intervention_closed("test_evt_456")
    await asyncio.sleep(0.2)

    # Clean shutdown
    await client.stop()
    client_task.cancel()
    server.close()
    await server.wait_closed()

    # Verify messages received by server
    types_received = [m.get("type") for m in received_by_server]
    assert "authenticate" in types_received
    assert "intervention_received" in types_received
    assert "intervention_closed" in types_received
