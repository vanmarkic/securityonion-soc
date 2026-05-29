"""Playbook API routes — playbook retrieval endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from src.ports.auth import Authorizer, Unauthorized
from src.services.playbook_service import PlaybookService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_playbook_service() -> PlaybookService:
    """Dependency that provides the PlaybookService.

    Intended to be overridden via app.dependency_overrides.
    """
    raise NotImplementedError("PlaybookService dependency not configured")


async def get_authorizer() -> Authorizer:
    """Dependency that provides the Authorizer.

    Intended to be overridden via app.dependency_overrides.
    """
    raise NotImplementedError("Authorizer dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


@router.get("/playbook/{playbook_id}")
async def get_playbook(
    playbook_id: str,
    service: PlaybookService = Depends(get_playbook_service),
    authorizer: Authorizer = Depends(get_authorizer),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        await authorizer.check_authorized(ctx.requestor_id, "read", "playbooks")
    except Unauthorized:
        raise HTTPException(status_code=403, detail="Forbidden") from None

    if not playbook_id:
        raise HTTPException(status_code=400, detail="playbook id required")

    try:
        result = await service.get_playbook(playbook_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None

    if result is None:
        return None

    return result.model_dump(by_alias=True, exclude_none=True)


@router.get("/playbook/detection/{detection_id}")
async def get_playbooks_for_detection(
    detection_id: str,
    raw: str = Query(default=""),
    service: PlaybookService = Depends(get_playbook_service),
    authorizer: Authorizer = Depends(get_authorizer),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        await authorizer.check_authorized(ctx.requestor_id, "read", "playbooks")
    except Unauthorized:
        raise HTTPException(status_code=403, detail="Forbidden") from None

    if not detection_id:
        raise HTTPException(status_code=400, detail="detection id required")

    raw_response = raw.lower() == "true"

    try:
        result, status = await service.get_playbooks_for_detection(
            detection_id, raw=raw_response,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None

    if status == 404:
        raise HTTPException(status_code=404, detail="Detection not found")

    if raw_response and isinstance(result, str):
        return PlainTextResponse(
            content=result,
            status_code=200,
            media_type="application/x-yaml",
        )

    if isinstance(result, list):
        return [pb.model_dump(by_alias=True, exclude_none=True) for pb in result]

    return result


@router.get("/playbook/event/{soc_id}")
async def get_event_specific_playbook(
    soc_id: str,
    service: PlaybookService = Depends(get_playbook_service),
    authorizer: Authorizer = Depends(get_authorizer),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        await authorizer.check_authorized(ctx.requestor_id, "read", "playbooks")
    except Unauthorized:
        raise HTTPException(status_code=403, detail="Forbidden") from None

    if not soc_id:
        raise HTTPException(status_code=400, detail="SOC id required")

    try:
        result, status = await service.get_event_specific_playbook(soc_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error") from None

    if status == 404:
        raise HTTPException(status_code=404, detail="Event not found")

    if isinstance(result, list):
        return [pb.model_dump(by_alias=True, exclude_none=True) for pb in result]

    return result
