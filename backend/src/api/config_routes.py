"""Config API routes — ported from Go server/confighandler.go."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from src.domain.config import Setting, is_valid_minion_id, is_valid_setting_id
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


@router.put("/config/")
@router.post("/config/")
async def put_setting(
    setting: Setting,
    service: ConfigService = Depends(get_config_service),
) -> Response:
    """Save a configuration setting."""
    if not is_valid_setting_id(setting.id):
        raise HTTPException(status_code=400, detail="Invalid setting")
    if setting.node_id and not is_valid_minion_id(setting.node_id):
        raise HTTPException(status_code=400, detail="Invalid setting")

    try:
        await service.update_setting(setting, remove=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(status_code=200)


@router.delete("/config/")
async def delete_config_bare(
    id: str = Query(default=""),
    minion: str = Query(default=""),
    service: ConfigService = Depends(get_config_service),
) -> Response:
    """Delete a configuration setting (query-param variant)."""
    if not id:
        raise HTTPException(status_code=400, detail="Missing setting ID")
    return await _do_delete_config(id, minion, service)


@router.delete("/config/{setting_id}/{minion}")
async def delete_config_with_minion(
    setting_id: str,
    minion: str,
    service: ConfigService = Depends(get_config_service),
) -> Response:
    """Delete a configuration setting for a specific minion."""
    return await _do_delete_config(setting_id, minion, service)


@router.delete("/config/{setting_id}")
async def delete_config_by_id(
    setting_id: str,
    service: ConfigService = Depends(get_config_service),
) -> Response:
    """Delete a configuration setting by ID."""
    return await _do_delete_config(setting_id, "", service)


async def _do_delete_config(
    setting_id: str, minion: str, service: ConfigService,
) -> Response:
    """Shared logic for all DELETE /config/ variants."""
    if not is_valid_setting_id(setting_id):
        raise HTTPException(status_code=400, detail="Invalid setting")
    if minion and not is_valid_minion_id(minion):
        raise HTTPException(status_code=400, detail="Invalid setting")

    setting = Setting(id=setting_id, node_id=minion)

    try:
        await service.update_setting(setting, remove=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(status_code=200)
