"""Events API routes — event search and alert acknowledgement."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.domain.event import (
    EventAckCriteria,
    EventSearchCriteria,
)
from src.services.events_service import EventsService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_events_service() -> EventsService:
    """Dependency that provides the EventsService.

    Intended to be overridden via app.dependency_overrides.
    """
    raise NotImplementedError("EventsService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AckRequest(BaseModel):
    """Body for POST /events/ack."""

    searchFilter: str = ""
    eventFilter: dict[str, Any] = {}
    dateRange: str = ""
    dateRangeFormat: str = ""
    timezone: str = ""
    escalate: bool = False
    acknowledge: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/events/")
async def get_events(
    request: Request,
    service: EventsService = Depends(get_events_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    if not service.is_eventstore_configured:
        return JSONResponse(
            content={"detail": "Method not supported"},
            status_code=405,
        )

    criteria = EventSearchCriteria()
    err = criteria.populate(
        query=request.query_params.get("query", ""),
        date_range=request.query_params.get("range", ""),
        date_range_format=request.query_params.get("format", ""),
        timezone_name=request.query_params.get("zone", "UTC"),
        metric_limit=request.query_params.get("metricLimit", "10"),
        event_limit=request.query_params.get("eventLimit", "25"),
    )
    if err is not None:
        return JSONResponse(content={"detail": err}, status_code=400)

    try:
        results = await service.search(criteria)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

    return JSONResponse(content={
        "totalEvents": results.total_events,
        "elapsedMs": results.elapsed_ms,
    })


@router.post("/events/ack")
async def post_ack(
    body: AckRequest,
    service: EventsService = Depends(get_events_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    if not service.is_eventstore_configured:
        return JSONResponse(
            content={"detail": "Method not supported"},
            status_code=405,
        )

    criteria = EventAckCriteria()
    criteria.search_filter = body.searchFilter
    criteria.event_filter = body.eventFilter
    criteria.date_range = body.dateRange
    criteria.date_range_format = body.dateRangeFormat
    criteria.timezone = body.timezone
    criteria.escalate = body.escalate
    criteria.acknowledge = body.acknowledge

    try:
        results = await service.acknowledge(criteria)
    except Exception:
        return JSONResponse(
            content={"detail": "The request could not be processed."},
            status_code=400,
        )

    return JSONResponse(content={
        "updatedCount": results.updated_count,
        "unchangedCount": results.unchanged_count,
        "elapsedMs": results.elapsed_ms,
    })
