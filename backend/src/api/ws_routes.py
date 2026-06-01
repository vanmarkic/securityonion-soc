"""WebSocket route — the manager real-time channel the Vue client connects to.

The frontend opens ``ws://<host><path>ws`` on load; when the socket opens it
flips its status to "connected" (clearing the "Disconnected from manager"
banner) and then sends ``{"Kind":"Ping"}`` every ~15s. Its ``onmessage`` handler
does ``publish(msg.Kind, msg.Object)`` to fan server-pushed events out to page
subscribers (jobs/nodes/cases/detections).

This implementation accepts the connection and drains client frames to keep it
open and detect disconnects — enough for the client to report "connected".
Server-initiated broadcasts (the Go ``Host.Broadcast(kind, channel, object)``
hub that pushes job/node/case/detection updates) are a larger subsystem and are
intentionally out of scope here; messages can be pushed on this socket once that
hub exists.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.debug("WebSocket client connected")
    try:
        # Read (and discard) client frames — chiefly the periodic
        # {"Kind":"Ping"} keepalive. Reading is what lets Starlette surface a
        # client disconnect; we do not need to reply for the client to stay
        # "connected".
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected")
