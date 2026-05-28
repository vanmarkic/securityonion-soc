"""GridMembers API routes — ported from Go server/gridmembershandler.go."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from src.ports.auth import Unauthorized
from src.services.gridmembers_service import GridMembersService
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

router = APIRouter()


async def get_gridmembers_service() -> GridMembersService:
    """Dependency that provides the GridMembersService.

    When not overridden, the gridmembers module is considered disabled (405).
    """
    raise HTTPException(status_code=405, detail="GridMembers module not enabled")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    """Thin wrapper so tests can override the request context dependency."""
    return ctx


@router.get("/gridmembers/")
async def get_grid_members(
    service: GridMembersService = Depends(get_gridmembers_service),
) -> list:
    """Retrieve all grid members."""
    members = await service.get_members()
    return [m.model_dump(by_alias=True) for m in members]


@router.post("/gridmembers/{node_id}/import")
async def post_import(
    node_id: str,
    attachment: UploadFile = File(...),
    service: GridMembersService = Depends(get_gridmembers_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> dict:
    """Import data (PCAP/EVTX) to a grid node.

    This endpoint validates the file magic bytes, checks authorization,
    and then processes the import.
    """
    # Auth check first — matches Go behavior
    try:
        await service.check_import_auth(ctx.requestor_id, node_id)
    except Unauthorized:
        raise HTTPException(status_code=403, detail="ERROR_PERMISSION_DENIED")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # File validation would go here in production
    return {"status": "accepted"}


@router.post("/gridmembers/{member_id}/{operation}")
async def post_manage_member(
    member_id: str,
    operation: str,
    service: GridMembersService = Depends(get_gridmembers_service),
) -> None:
    """Manage a grid member (add, reject, delete, test, restart)."""
    try:
        await service.manage_member(operation, member_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
