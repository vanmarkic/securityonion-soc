"""Users API routes -- ported from Go usershandler.go."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from src.domain.user import User
from src.services.users_service import (
    InvalidId,
    InvalidRole,
    InvalidToggle,
    UsersService,
    ValidationError,
)
from src.shared.context import RequestContext
from src.shared.middleware import get_request_context

router = APIRouter()


# ------------------------------------------------------------------
# Dependencies (overrideable via app.dependency_overrides)
# ------------------------------------------------------------------


async def get_users_service() -> UsersService:
    raise NotImplementedError("UsersService dependency not configured")


async def get_request_context_dep(
    ctx: RequestContext = Depends(get_request_context),
) -> RequestContext:
    return ctx


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class PasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    password: str = ""


# ------------------------------------------------------------------
# GET /users/
# ------------------------------------------------------------------


@router.get("/users/")
async def get_users(
    service: UsersService = Depends(get_users_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        users = await service.get_users()
    except Exception:
        raise HTTPException(status_code=500) from None
    return [u.model_dump(by_alias=True) for u in users]


# ------------------------------------------------------------------
# POST /users/
# ------------------------------------------------------------------


@router.post("/users/")
async def create_user(
    user: User,
    service: UsersService = Depends(get_users_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.create_user(user)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return result.model_dump(by_alias=True)


# ------------------------------------------------------------------
# POST /users/{id}/role/{role}
# ------------------------------------------------------------------


@router.post("/users/{user_id}/role/{role}")
async def add_role(
    user_id: str,
    role: str,
    service: UsersService = Depends(get_users_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.add_role(user_id, role)
    except (InvalidId, InvalidRole) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# PUT /users/sync
# ------------------------------------------------------------------


@router.put("/users/sync")
async def sync_users(
    service: UsersService = Depends(get_users_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.sync_users()
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# PUT /users/{id}
# ------------------------------------------------------------------


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    user: User,
    service: UsersService = Depends(get_users_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> Any:
    try:
        result = await service.update_profile(user_id, user)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None
    return result.model_dump(by_alias=True)


# ------------------------------------------------------------------
# PUT /users/{id}/password
# ------------------------------------------------------------------


@router.put("/users/{user_id}/password")
async def reset_password(
    user_id: str,
    body: PasswordRequest,
    service: UsersService = Depends(get_users_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.reset_password(user_id, body.password)
    except InvalidId as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# PUT /users/{id}/{toggle}
# ------------------------------------------------------------------


@router.put("/users/{user_id}/{toggle}")
async def toggle_user(
    user_id: str,
    toggle: str,
    service: UsersService = Depends(get_users_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.toggle_user(user_id, toggle)
    except (InvalidId, InvalidToggle) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# DELETE /users/{id}
# ------------------------------------------------------------------


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    service: UsersService = Depends(get_users_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.delete_user(user_id)
    except InvalidId as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None


# ------------------------------------------------------------------
# DELETE /users/{id}/role/{role}
# ------------------------------------------------------------------


@router.delete("/users/{user_id}/role/{role}")
async def delete_user_role(
    user_id: str,
    role: str,
    service: UsersService = Depends(get_users_service),
    ctx: RequestContext = Depends(get_request_context_dep),
) -> None:
    try:
        await service.delete_role(user_id, role)
    except (InvalidId, InvalidRole) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=500) from None
