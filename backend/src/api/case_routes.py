"""Case API routes — all /case/ endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from src.domain.case import Artifact, AttachEventCriteria, Case, Comment
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


@router.post("/case/events")
async def create_events(
    criteria: AttachEventCriteria,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> JSONResponse:
    """Async attach events to a case. Returns 202 Accepted."""
    try:
        count = await service.attach_events(criteria)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return JSONResponse(status_code=202, content={"count": count})


@router.post("/case/tasks")
async def create_task(
    artifact: Artifact,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    """Alias for POST /case/artifacts."""
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


@router.get("/case/comments")
async def get_comments_query(
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    """Get comments by query param (no path param)."""
    try:
        results = await service.get_comments(id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return [c.model_dump(by_alias=True) for c in results]


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


@router.get("/case/events")
async def get_events_query(
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    """Get related events by query param (no path param)."""
    try:
        results = await service.get_related_events(id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return [e.model_dump(by_alias=True) for e in results]


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


@router.get("/case/tasks")
@router.get("/case/artifactstream")
async def get_artifact_stream_query(
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Response:
    """Download artifact stream by query param."""
    return await _copy_artifact_stream(id, service)


@router.get("/case/tasks/{artifact_id}")
@router.get("/case/artifactstream/{artifact_id}")
async def get_artifact_stream(
    artifact_id: str,
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Response:
    """Download artifact stream by path param."""
    return await _copy_artifact_stream(artifact_id, service)


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


@router.get("/case/history")
async def get_history_query(
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    """Get case history by query param (no path param)."""
    try:
        result = await service.get_case_history(id)
    except Exception:
        raise HTTPException(status_code=404, detail="Case not found")
    return result


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


# NOTE: /case/{case_id} MUST come after all /case/comments, /case/events,
# /case/tasks, /case/artifacts*, /case/history, /case/artifactstream routes
# because FastAPI matches routes in declaration order and {case_id} would
# swallow those sub-resource paths.

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


@router.put("/case/tasks")
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

@router.delete("/case/comments")
async def delete_comment_query(
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    """Delete comment by query param."""
    try:
        await service.delete_comment(id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


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


@router.delete("/case/events")
async def delete_event_query(
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    """Delete related event by query param."""
    try:
        await service.delete_related_event(id)
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


@router.delete("/case/tasks")
@router.delete("/case/artifacts")
async def delete_artifact_query(
    id: str = Query(default=""),
    service: CaseService = Depends(get_case_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    """Delete artifact/task by query param."""
    try:
        await service.delete_artifact(id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/case/tasks/{artifact_id}")
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


# -- Helpers --

async def _copy_artifact_stream(artifact_id: str, service: CaseService) -> Response:
    """Fetch artifact + its stream, return as binary download.

    Matches Go's copyArtifactStream behavior.
    """
    artifact = await service.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    stream = await service.get_artifact_stream(artifact.stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Artifact stream not found")

    content = stream.read()
    content_length = artifact.stream_len
    filename = artifact.value

    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(content_length),
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Transfer-Encoding": "binary",
        },
    )
