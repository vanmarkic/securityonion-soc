"""Case API routes — all /case/ endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from src.domain.case import Artifact, Case, Comment
from src.services.case_service import CaseService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_case_service() -> CaseService:
    """Dependency that provides the CaseService.

    Intended to be overridden via app.dependency_overrides in production wiring
    and tests.
    """
    raise NotImplementedError("CaseService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


# -- Create --

@router.post("/case/")
async def create_case(
    case: Case,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.create_case(case)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return result.model_dump(by_alias=True)


@router.post("/case/comments")
async def create_comment(
    comment: Comment,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.create_comment(comment)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return result.model_dump(by_alias=True)


@router.post("/case/artifacts")
async def create_artifact(
    artifact: Artifact,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.create_artifact(artifact)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return result.model_dump(by_alias=True)


# -- Read --

@router.get("/case/")
async def get_cases(
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.get_case(id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    if result is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return result.model_dump(by_alias=True)


@router.get("/case/{case_id}")
async def get_case(
    case_id: str,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.get_case(case_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    if result is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return result.model_dump(by_alias=True)


@router.get("/case/comments/{case_id}")
async def get_comments(
    case_id: str,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        results = await service.get_comments(case_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return [c.model_dump(by_alias=True) for c in results]


@router.get("/case/events/{case_id}")
async def get_events(
    case_id: str,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        results = await service.get_related_events(case_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return [e.model_dump(by_alias=True) for e in results]


@router.get("/case/artifacts/{group_type}/{group_id}/{artifact_id}")
async def get_artifact_by_id(
    group_type: str,
    group_id: str,
    artifact_id: str,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        results = await service.get_artifacts(artifact_id, group_type, group_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return [a.model_dump(by_alias=True) for a in results]


@router.get("/case/artifacts/{group_type}/{group_id}")
async def get_artifacts_by_group(
    group_type: str,
    group_id: str,
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        results = await service.get_artifacts(id, group_type, group_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return [a.model_dump(by_alias=True) for a in results]


@router.get("/case/artifacts/{group_type}")
async def get_artifacts_by_type(
    group_type: str,
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        results = await service.get_artifacts(id, group_type, "")
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return [a.model_dump(by_alias=True) for a in results]


@router.get("/case/history/{case_id}")
async def get_history(
    case_id: str,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.get_case_history(case_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Case not found")
    return result


# -- Update --

@router.put("/case/")
async def update_case(
    case: Case,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.update_case(case)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return result.model_dump(by_alias=True)


@router.put("/case/comments")
async def update_comment(
    comment: Comment,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.update_comment(comment)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return result.model_dump(by_alias=True)


@router.put("/case/artifacts")
async def update_artifact(
    artifact: Artifact,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.update_artifact(artifact)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return result.model_dump(by_alias=True)


# -- Delete --

@router.delete("/case/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.delete_comment(comment_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/case/events/{event_id}")
async def delete_event(
    event_id: str,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.delete_related_event(event_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/case/artifacts/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.delete_artifact(artifact_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
