"""Info API routes — GET /info/ endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.services.info_service import InfoService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

router = APIRouter()


async def get_info_service() -> InfoService:
    """Dependency that provides the InfoService.

    Intended to be overridden via app.dependency_overrides in production wiring
    and tests.
    """
    raise NotImplementedError("InfoService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


@router.get("/info/")
async def get_info(
    service: InfoService = Depends(get_info_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> dict[str, Any]:
    """Return system info for the authenticated user."""
    info = await service.get_info(user_id=ctx.requestor_id)
    return info.model_dump(by_alias=True)
