"""Tests for the /ws manager WebSocket endpoint."""

from starlette.testclient import TestClient

from src.main import app


def test_ws_accepts_connection_and_drains_pings():
    # The Vue client opens the socket (→ "connected") and periodically sends
    # {"Kind":"Ping"}. The endpoint must accept and keep the connection open.
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text('{"Kind":"Ping"}')
        ws.send_text('{"Kind":"Ping"}')
        # No exception → the server accepted and is draining frames.


def test_ws_route_is_registered_at_root_not_under_api():
    # Frontend wsUrl resolves to /ws (root); /api/ws must NOT be the path.
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/ws" in paths
    assert "/api/ws" not in paths


def test_ws_handles_client_disconnect_cleanly():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text('{"Kind":"Ping"}')
    # Exiting the context closes the client; the server must handle
    # WebSocketDisconnect without raising. Reconnecting again still works:
    with client.websocket_connect("/ws") as ws:
        ws.send_text('{"Kind":"Ping"}')
