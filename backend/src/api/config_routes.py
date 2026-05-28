"""Config API routes — ported from Go server/confighandler.go."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from src.services.config_service import ConfigService

router = APIRouter()


async def get_config_service() -> ConfigService:
    """Dependency that provides the ConfigService.

    Intended to be overridden via app.dependency_overrides in production wiring
    and tests. When not overridden, the config module is considered disabled (405).
    """
    raise HTTPException(status_code=405, detail="Config module not enabled")


@router.get("/config/")
async def get_config(
    advanced: bool = Query(default=False),
    service: ConfigService = Depends(get_config_service),
) -> list:
    """Retrieve configuration settings."""
    return await service.get_settings(advanced)


@router.put("/config/sync")
@router.post("/config/sync")
async def put_sync(
    service: ConfigService = Depends(get_config_service),
) -> Response:
    """Synchronize all settings to the grid."""
    await service.sync_settings()
    return Response(status_code=200)


@router.put("/config/sync/{module}")
async def put_sync_module(
    module: str,
    force: bool = Query(default=False),
    service: ConfigService = Depends(get_config_service),
) -> Response:
    """Synchronize a specific module's state."""
    try:
        await service.sync_module(module, force)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(status_code=200)
