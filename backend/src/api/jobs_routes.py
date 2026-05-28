"""Jobs API routes — list jobs by kind and parameters."""

from __future__ import annotations

import json as json_lib
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.services.job_service import JobService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_job_service() -> JobService:
    """Dependency that provides the JobService.

    Intended to be overridden via app.dependency_overrides.
    """
    raise NotImplementedError("JobService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


@router.get("/jobs/")
async def get_jobs(
    request: Request,
    service: JobService = Depends(get_job_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    kind = request.query_params.get("kind", "")
    params_str = request.query_params.get("parameters", "")

    params: dict[str, Any] = {}
    if params_str:
        try:
            params = json_lib.loads(params_str)
        except (json_lib.JSONDecodeError, TypeError):
            return JSONResponse(
                content={"detail": "Invalid parameters JSON"},
                status_code=400,
            )

    jobs = service.get_jobs(kind, params)
    return [j.model_dump(by_alias=True) for j in jobs]
