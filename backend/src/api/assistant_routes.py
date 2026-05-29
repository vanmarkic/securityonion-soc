"""Assistant API routes — all /assistant/ endpoints (11 routes)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from src.domain.assistant import IncomingMessage, ToolRequest, UpdateSessionRequest
from src.services.assistant_service import AssistantService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_assistant_service() -> AssistantService:
    """Dependency that provides the AssistantService.

    Intended to be overridden via app.dependency_overrides in production wiring
    and tests.
    """
    raise NotImplementedError("AssistantService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


# -- POST /assistant/chat --

@router.post("/assistant/chat")
async def post_chat(
    incoming: IncomingMessage,
    request: Request,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
    accept: str = Header(default="application/json"),
) -> Any:
    if service.airgap_enabled:
        raise HTTPException(status_code=500, detail="ERROR_SERVICE_NOT_AVAILABLE")

    entity_type = request.query_params.get("entityType", "")
    entity_id = request.query_params.get("entityId", "")

    streaming = accept.strip().lower() == "text/event-stream"

    if streaming:
        stream = service.chat_stream(
            incoming, ctx.requestor_id,
            entity_type=entity_type, entity_id=entity_id,
        )
        return StreamingResponse(stream, media_type="text/event-stream")

    try:
        result = await service.chat(
            incoming, ctx.requestor_id,
            entity_type=entity_type, entity_id=entity_id,
        )
    except Exception as e:
        err_msg = str(e)
        if err_msg == "ERROR_ASSISTANT_REQUEST_TOO_LARGE":
            raise HTTPException(status_code=400, detail=err_msg) from None
        raise HTTPException(status_code=500, detail="ERROR_UPSTREAM_SERVICE_ERROR") from None
    return result


# -- POST /assistant/tool/{name} --

@router.post("/assistant/tool/{name}")
async def post_tool(
    name: str,
    tool_req: ToolRequest,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
    accept: str = Header(default="application/json"),
) -> Any:
    if service.airgap_enabled:
        raise HTTPException(status_code=500, detail="ERROR_SERVICE_NOT_AVAILABLE")

    streaming = accept.strip().lower() == "text/event-stream"

    try:
        result = await service.execute_tool(name, tool_req, streaming=streaming)
    except Exception as e:
        err_msg = str(e)
        if err_msg == "ERROR_ASSISTANT_REQUEST_TOO_LARGE":
            raise HTTPException(status_code=400, detail=err_msg) from None
        raise HTTPException(status_code=500, detail="ERROR_UPSTREAM_SERVICE_ERROR") from None

    if streaming:
        return StreamingResponse(result, media_type="text/event-stream")
    return result


# -- GET /assistant/balance/{model_and_adapter} --

@router.get("/assistant/balance/{model_and_adapter:path}")
async def get_balance(
    model_and_adapter: str,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    if service.airgap_enabled:
        raise HTTPException(status_code=500, detail="ERROR_SERVICE_NOT_AVAILABLE")

    try:
        result = await service.get_balance(model_and_adapter)
    except Exception:
        raise HTTPException(status_code=500, detail="ERROR_UPSTREAM_SERVICE_ERROR") from None

    if result is None:
        raise HTTPException(status_code=500)
    return result


# -- GET /assistant/sessions --

@router.get("/assistant/sessions")
async def get_sessions(
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        return await service.get_sessions(ctx.requestor_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None


# -- GET /assistant/sessions/{sessionId} --

@router.get("/assistant/sessions/{sessionId}")
async def get_session_details(
    sessionId: str,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    if not sessionId:
        raise HTTPException(status_code=400, detail="sessionId is required")

    try:
        return await service.get_session_details(sessionId)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None


# -- PUT /assistant/sessions/{sessionId} --

@router.put("/assistant/sessions/{sessionId}")
async def update_session(
    sessionId: str,
    update_req: UpdateSessionRequest,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Response:
    if not sessionId:
        raise HTTPException(status_code=400, detail="sessionId is required")

    try:
        status, error = await service.update_session(sessionId, update_req)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None

    if error is not None:
        if status == 404:
            raise HTTPException(status_code=404, detail=error)
        if status == 409:
            raise HTTPException(status_code=409, detail=error)
        raise HTTPException(status_code=status, detail=error)

    return Response(status_code=204)


# -- DELETE /assistant/sessions/{sessionId} --

@router.delete("/assistant/sessions/{sessionId}")
async def delete_session(
    sessionId: str,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Response:
    if not sessionId:
        raise HTTPException(status_code=400, detail="sessionId is required")

    try:
        await service.delete_session(sessionId)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None

    return Response(status_code=204)


# -- GET /assistant/admin/stats --

@router.get("/assistant/admin/stats")
async def get_usage(
    request: Request,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    range_str = request.query_params.get("range", "")
    format_str = request.query_params.get("format", "")
    zone_str = request.query_params.get("zone", "")

    start, end = _parse_date_range(range_str, format_str, zone_str)

    try:
        return await service.get_usage(start, end)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None


# -- GET /assistant/admin/sessions --

@router.get("/assistant/admin/sessions")
async def get_all_sessions(
    request: Request,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    range_str = request.query_params.get("range", "")
    format_str = request.query_params.get("format", "")
    zone_str = request.query_params.get("zone", "")

    start, end = _parse_date_range(range_str, format_str, zone_str)

    try:
        return await service.get_all_sessions(start, end)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None


# -- GET /assistant/admin/{userId}/sessions --

@router.get("/assistant/admin/{userId}/sessions")
async def get_user_sessions(
    userId: str,
    request: Request,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    range_str = request.query_params.get("range", "")
    format_str = request.query_params.get("format", "")
    zone_str = request.query_params.get("zone", "")

    start, end = _parse_date_range(range_str, format_str, zone_str)

    try:
        return await service.get_all_sessions(start, end, user_id=userId)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None


# -- GET /assistant/admin/{userId}/sessions/{sessionId}/history --

@router.get("/assistant/admin/{userId}/sessions/{sessionId}/history")
async def get_session_history_admin(
    userId: str,
    sessionId: str,
    service: AssistantService = Depends(get_assistant_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        history, status, error = await service.get_session_history_admin(userId, sessionId)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None

    if error is not None:
        raise HTTPException(status_code=status, detail=error)
    return history


# -- Helpers --

def _parse_date_range(
    range_str: str, format_str: str, zone_str: str,
) -> tuple[datetime, datetime]:
    """Parse a date range string into start and end datetimes.

    Simplified version of Go's util.ParseDateRange.
    Expected format: "2025-01-01 00:00:00 - 2025-01-31 23:59:59"
    """
    if not range_str:
        # Default to a wide range if not specified
        return datetime.min, datetime.max

    try:
        parts = range_str.split(" - ", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="invalid date range format")

        fmt = format_str or "%Y-%m-%d %H:%M:%S"
        start = datetime.strptime(parts[0].strip(), fmt)
        end = datetime.strptime(parts[1].strip(), fmt)
        return start, end
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid date range: {e}") from None
