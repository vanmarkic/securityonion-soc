"""Util API routes — ported from Go server/utilhandler.go."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from src.services.util_service import UtilService

router = APIRouter()


async def get_util_service() -> UtilService:
    """Dependency that provides the UtilService.

    Intended to be overridden via app.dependency_overrides in production wiring
    and tests.
    """
    raise NotImplementedError("UtilService dependency not configured")


@router.put("/util/reverse-lookup")
async def put_reverse_lookup(
    request: Request,
    service: UtilService = Depends(get_util_service),
) -> dict[str, list[str]]:
    """Perform reverse DNS lookup on a list of IP addresses."""
    try:
        body: list[str] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not isinstance(body, list):
        raise HTTPException(status_code=400, detail="Expected a JSON array of IP strings")

    return await service.reverse_lookup(body)
