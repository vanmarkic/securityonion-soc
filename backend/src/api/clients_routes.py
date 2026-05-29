"""Clients API routes -- ported from Go clientshandler.go."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.domain.client import Client
from src.services.clients_service import (
    ClientsService,
    InvalidClientId,
    InvalidPermission,
    ValidationError,
)
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

router = APIRouter()


# ------------------------------------------------------------------
# Dependencies (overrideable via app.dependency_overrides)
# ------------------------------------------------------------------


async def get_clients_service() -> ClientsService:
    raise NotImplementedError("ClientsService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    return ctx


# ------------------------------------------------------------------
# GET /clients/
# ------------------------------------------------------------------


@router.get("/clients/")
async def get_clients(
    service: ClientsService = Depends(get_clients_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        clients = await service.get_clients()
    except Exception:
        raise HTTPException(status_code=400) from None
    return [c.model_dump(by_alias=True) for c in clients]


# ------------------------------------------------------------------
# POST /clients/
# ------------------------------------------------------------------


@router.post("/clients/")
async def create_client(
    client_obj: Client,
    service: ClientsService = Depends(get_clients_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.create_client(client_obj)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return result.model_dump(by_alias=True)


# ------------------------------------------------------------------
# POST /clients/{id}/permission/{resource}/{privilege}
# ------------------------------------------------------------------


@router.post("/clients/{client_id}/permission/{resource}/{privilege}")
async def add_permission(
    client_id: str,
    resource: str,
    privilege: str,
    service: ClientsService = Depends(get_clients_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.add_permission(client_id, resource, privilege)
    except (InvalidClientId, InvalidPermission) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# PUT /clients/{id}
# ------------------------------------------------------------------


@router.put("/clients/{client_id}")
async def update_client(
    client_id: str,
    client_obj: Client,
    service: ClientsService = Depends(get_clients_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.update_client(client_id, client_obj)
    except (InvalidClientId, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return result.model_dump(by_alias=True)


# ------------------------------------------------------------------
# PUT /clients/{id}/secret
# ------------------------------------------------------------------


@router.put("/clients/{client_id}/secret")
async def generate_secret(
    client_id: str,
    service: ClientsService = Depends(get_clients_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.generate_secret(client_id)
    except InvalidClientId as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return result.model_dump(by_alias=True)


# ------------------------------------------------------------------
# DELETE /clients/{id}
# ------------------------------------------------------------------


@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: str,
    service: ClientsService = Depends(get_clients_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.delete_client(client_id)
    except InvalidClientId as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# DELETE /clients/{id}/permission/{resource}/{privilege}
# ------------------------------------------------------------------


@router.delete("/clients/{client_id}/permission/{resource}/{privilege}")
async def delete_permission(
    client_id: str,
    resource: str,
    privilege: str,
    service: ClientsService = Depends(get_clients_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.delete_permission(client_id, resource, privilege)
    except (InvalidClientId, InvalidPermission) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None
