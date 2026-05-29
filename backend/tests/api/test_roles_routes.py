"""Tests for roles routes -- ported from Go roleshandler.go behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.roles_routes import get_request_context_dep, get_roles_service
from src.main import app
from src.services.roles_service import RolesService
from src.shared.context import RequestContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_context() -> RequestContext:
    return RequestContext(requestor_id="test-user-id", username="tester")


def _make_service(rolestore: Any = None) -> RolesService:
    if rolestore is None:
        rolestore = AsyncMock()
    return RolesService(rolestore=rolestore)


@pytest.fixture
def mock_rolestore():
    return AsyncMock()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _wire(service: RolesService) -> None:
    app.dependency_overrides[get_roles_service] = lambda: service
    app.dependency_overrides[get_request_context_dep] = _fake_context


# ===========================================================================
# GET /roles/ — getRoles
# ===========================================================================


class TestGetRoles:
    async def test_sunny_day(self, client, mock_rolestore):
        mock_rolestore.get_roles = AsyncMock(
            return_value=["admin", "analyst", "auditor"]
        )
        service = _make_service(rolestore=mock_rolestore)
        _wire(service)

        resp = await client.get("/api/roles/")
        assert resp.status_code == 200
        data = resp.json()
        assert data == ["admin", "analyst", "auditor"]

    async def test_empty_list(self, client, mock_rolestore):
        mock_rolestore.get_roles = AsyncMock(return_value=[])
        service = _make_service(rolestore=mock_rolestore)
        _wire(service)

        resp = await client.get("/api/roles/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_error_500(self, client, mock_rolestore):
        mock_rolestore.get_roles = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(rolestore=mock_rolestore)
        _wire(service)

        resp = await client.get("/api/roles/")
        assert resp.status_code == 500


# ===========================================================================
# GET /roles/permissions — getPermissions
# ===========================================================================


class TestGetPermissions:
    async def test_sunny_day(self, client, mock_rolestore):
        mock_rolestore.get_permissions = AsyncMock(
            return_value={"events": ["read", "write"], "cases": ["read"]}
        )
        service = _make_service(rolestore=mock_rolestore)
        _wire(service)

        resp = await client.get("/api/roles/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == ["read", "write"]
        assert data["cases"] == ["read"]

    async def test_empty_permissions(self, client, mock_rolestore):
        mock_rolestore.get_permissions = AsyncMock(return_value={})
        service = _make_service(rolestore=mock_rolestore)
        _wire(service)

        resp = await client.get("/api/roles/permissions")
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_error_500(self, client, mock_rolestore):
        mock_rolestore.get_permissions = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(rolestore=mock_rolestore)
        _wire(service)

        resp = await client.get("/api/roles/permissions")
        assert resp.status_code == 500
