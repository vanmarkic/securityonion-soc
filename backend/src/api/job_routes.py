"""Job API routes — single job CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.domain.job import Job
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


@router.get("/job/")
async def get_job_by_query(
    request: Request,
    service: JobService = Depends(get_job_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    raw_id = request.query_params.get("jobId", "")
    try:
        job_id = int(raw_id)
    except (ValueError, TypeError):
        return JSONResponse(
            content={"detail": "Invalid job ID"},
            status_code=400,
        )

    job = service.get_job(job_id)
    if job is None:
        return JSONResponse(content=None, status_code=404)

    return job.model_dump(by_alias=True)


@router.get("/job/{jobId}")
async def get_job_by_path(
    jobId: str,
    service: JobService = Depends(get_job_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        job_id = int(jobId)
    except (ValueError, TypeError):
        return JSONResponse(
            content={"detail": "Invalid job ID"},
            status_code=400,
        )

    job = service.get_job(job_id)
    if job is None:
        return JSONResponse(content=None, status_code=404)

    return job.model_dump(by_alias=True)


@router.post("/job/", status_code=201)
async def create_job(
    body: dict[str, Any],
    service: JobService = Depends(get_job_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    job = service.create_job()
    # Apply fields from body
    for key, value in body.items():
        if hasattr(job, key):
            setattr(job, key, value)
        # Handle alias mappings
        alias_map = {
            "nodeId": "node_id",
            "sensorId": "legacy_sensor_id",
            "fileExtension": "file_extension",
            "userId": "user_id",
            "failCount": "fail_count",
            "createTime": "create_time",
            "completeTime": "complete_time",
            "failTime": "fail_time",
        }
        if key in alias_map and hasattr(job, alias_map[key]):
            setattr(job, alias_map[key], value)

    try:
        await service.add_job(job)
    except Exception:
        return JSONResponse(
            content={"detail": "The request could not be processed."},
            status_code=400,
        )

    return job.model_dump(by_alias=True)


@router.put("/job/")
async def update_job(
    body: dict[str, Any],
    service: JobService = Depends(get_job_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    job = Job(**body)

    try:
        await service.update_job(job)
    except Exception:
        return JSONResponse(content=None, status_code=404)

    return job.model_dump(by_alias=True)


@router.delete("/job/{jobId}")
async def delete_job(
    jobId: str,
    service: JobService = Depends(get_job_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        job_id = int(jobId)
    except (ValueError, TypeError):
        return JSONResponse(
            content={"detail": "Invalid job ID"},
            status_code=400,
        )

    result = await service.delete_job(job_id)
    if result[1] is not None:
        raise HTTPException(status_code=500, detail=result[1])

    return JSONResponse(content=None, status_code=200)
