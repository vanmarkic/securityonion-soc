"""Query API routes — query manipulation and active query management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from src.services.query_service import QueryNotFoundError, QueryService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_query_service() -> QueryService:
    """Dependency that provides the QueryService.

    Intended to be overridden via app.dependency_overrides.
    """
    raise NotImplementedError("QueryService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


@router.get("/query/active")
async def get_active_queries(
    filter: str = Query(default="false"),
    service: QueryService = Depends(get_query_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    if not service.is_licensed:
        return PlainTextResponse(
            content="ERROR_LICENSE_INVALID",
            status_code=400,
        )

    filter_internal = filter.lower() == "true"
    try:
        results = await service.get_active_queries(filter_internal)
    except Exception:
        raise HTTPException(status_code=400, detail="The request could not be processed.")
    return [r.to_dict() for r in results]


@router.post("/query/cancel/{query_id}")
async def cancel_query(
    query_id: str,
    service: QueryService = Depends(get_query_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    if not service.is_licensed:
        return PlainTextResponse(
            content="ERROR_LICENSE_INVALID",
            status_code=400,
        )

    try:
        await service.cancel_query(query_id)
    except QueryNotFoundError:
        return PlainTextResponse(
            content="ERROR_QUERY_NOT_FOUND",
            status_code=404,
        )
    except Exception:
        return PlainTextResponse(
            content="The request could not be processed.",
            status_code=400,
        )
    return PlainTextResponse(content="", status_code=200)


@router.get("/query/{operation}")
async def get_query(
    operation: str,
    request: Request,
    service: QueryService = Depends(get_query_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    query_str = request.query_params.get("query", "")
    field = request.query_params.get("field", "")
    scalar = request.query_params.get("scalar", "false") == "true"
    mode = request.query_params.get("mode", "")
    value = request.query_params.get("value", "")
    condense = request.query_params.get("condense", "false") == "true"
    group = request.query_params.get("group", "0")

    if operation == "filtered":
        if value:
            altered, err = service.build_filtered_query(
                query_str, field, value, scalar, mode, condense,
            )
        else:
            # Check for value[] params
            values = request.query_params.getlist("value[]")
            altered = query_str
            err = None
            for v in values:
                altered, err = service.build_filtered_query(
                    altered, field, v, scalar, mode, condense,
                )
                if err:
                    break
    elif operation == "grouped":
        try:
            group_idx = int(group)
        except ValueError:
            group_idx = 0
        altered, err = service.build_grouped_query(query_str, field, group_idx)
    elif operation == "sorted":
        altered, err = service.build_sorted_query(query_str, field)
    else:
        return PlainTextResponse(
            content="Unsupported query operation",
            status_code=400,
        )

    if err:
        return PlainTextResponse(content=err, status_code=400)

    escaped = altered.replace("\\", "\\\\").replace('"', '\\"')
    return PlainTextResponse(content=f'"{escaped}"', status_code=200)
