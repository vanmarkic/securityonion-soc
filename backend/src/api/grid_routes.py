"""Grid API routes — ported from Go server/gridhandler.go."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.services.grid_service import GridService

router = APIRouter()


async def get_grid_service() -> GridService:
    """Dependency that provides the GridService.

    Intended to be overridden via app.dependency_overrides in production wiring
    and tests.
    """
    raise NotImplementedError("GridService dependency not configured")


@router.get("/grid/")
async def get_nodes(
    assignedGridId: str = Query(default=""),
    service: GridService = Depends(get_grid_service),
) -> list[dict]:
    """Retrieve the list of grid nodes."""
    return await service.get_nodes(assignedGridId)


@router.get("/grid/status")
async def get_status(
    assignedGridId: str = Query(default=""),
    service: GridService = Depends(get_grid_service),
) -> dict:
    """Retrieve the grid status summary."""
    return await service.get_status(assignedGridId)
