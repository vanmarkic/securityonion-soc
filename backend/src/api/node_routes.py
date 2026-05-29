"""Node API routes — agent node check-in."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.domain.node import Node
from src.services.node_service import NodeService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_node_service() -> NodeService:
    """Dependency that provides the NodeService.

    Intended to be overridden via app.dependency_overrides.
    """
    raise NotImplementedError("NodeService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class NodeCheckinRequest(BaseModel):
    """Body for POST /node/ — node check-in."""

    id: str = ""
    description: str = ""
    address: str = ""
    role: str = ""
    model: str = ""
    status: str = ""
    version: str = ""
    connection_status: str = Field(default="", alias="connectionStatus")
    raid_status: str = Field(default="", alias="raidStatus")
    process_status: str = Field(default="", alias="processStatus")
    process_json: str = Field(default="", alias="processJson")
    uptime_seconds: int = Field(default=0, alias="uptimeSeconds")
    production_eps: int = Field(default=0, alias="productionEps")
    consumption_eps: int = Field(default=0, alias="consumptionEps")
    failed_events: int = Field(default=0, alias="failedEvents")
    eventstore_status: str = Field(default="", alias="eventstoreStatus")
    os_needs_restart: int = Field(default=0, alias="osNeedsRestart")
    os_uptime_seconds: int = Field(default=0, alias="osUptimeSeconds")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/node/")
async def post_node(
    body: NodeCheckinRequest,
    service: NodeService = Depends(get_node_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    node = Node(body.id)
    node.description = body.description
    node.address = body.address
    node.role = body.role
    node.status = body.status
    node.version = body.version
    node.connection_status = body.connection_status
    node.raid_status = body.raid_status
    node.process_status = body.process_status
    node.process_json = body.process_json
    node.uptime_seconds = body.uptime_seconds
    node.production_eps = body.production_eps
    node.consumption_eps = body.consumption_eps
    node.failed_events = body.failed_events
    node.eventstore_status = body.eventstore_status
    node.os_needs_restart = body.os_needs_restart
    node.os_uptime_seconds = body.os_uptime_seconds
    if body.model:
        node.set_model(body.model)

    try:
        _updated_node, job = await service.checkin(node)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None

    if job is None:
        return JSONResponse(content=None, status_code=200)

    return job.model_dump(by_alias=True)
