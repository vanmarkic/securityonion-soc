"""Roles API routes -- ported from Go roleshandler.go."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.services.roles_service import RolesService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

router = APIRouter()


# ------------------------------------------------------------------
# Dependencies (overrideable via app.dependency_overrides)
# ------------------------------------------------------------------


async def get_roles_service() -> RolesService:
    raise NotImplementedError("RolesService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    return ctx


# ------------------------------------------------------------------
# GET /roles/
# ------------------------------------------------------------------


@router.get("/roles/")
async def get_roles(
    service: RolesService = Depends(get_roles_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        return await service.get_roles()
    except Exception:
        raise HTTPException(status_code=500)


# ------------------------------------------------------------------
# GET /roles/permissions
# ------------------------------------------------------------------


@router.get("/roles/permissions")
async def get_permissions(
    service: RolesService = Depends(get_roles_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        return await service.get_permissions()
    except Exception:
        raise HTTPException(status_code=500)
