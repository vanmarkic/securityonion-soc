"""Tests for users routes -- ported from Go usershandler.go behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.domain.user import User
from src.main import app
from src.api.users_routes import get_users_service, get_request_context_dep
from src.services.users_service import UsersService
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_context() -> RequestContext:
    return RequestContext(requestor_id="test-user-id", username="tester")


def _make_service(
    userstore: Any = None,
    admin_userstore: Any = None,
    rolestore: Any = None,
) -> UsersService:
    if userstore is None:
        userstore = AsyncMock()
    if admin_userstore is None:
        admin_userstore = AsyncMock()
    if rolestore is None:
        rolestore = AsyncMock()
    return UsersService(
        userstore=userstore,
        admin_userstore=admin_userstore,
        rolestore=rolestore,
    )


@pytest.fixture
def mock_userstore():
    return AsyncMock()


@pytest.fixture
def mock_admin_userstore():
    return AsyncMock()


@pytest.fixture
def mock_rolestore():
    store = AsyncMock()
    store.ensure_default_role_for_user = AsyncMock(return_value=None)
    return store


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _wire(service: UsersService) -> None:
    app.dependency_overrides[get_users_service] = lambda: service
    app.dependency_overrides[get_request_context_dep] = _fake_context


# ===========================================================================
# GET /users/ — getUsers
# ===========================================================================


class TestGetUsers:
    async def test_sunny_day(self, client, mock_userstore, mock_rolestore):
        users = [
            User(id="u1", email="a@b.com"),
            User(id="u2", email="c@d.com"),
        ]
        mock_userstore.get_users = AsyncMock(return_value=users)
        service = _make_service(userstore=mock_userstore, rolestore=mock_rolestore)
        _wire(service)

        resp = await client.get("/api/users/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "u1"

    async def test_ensure_default_role_error_500(self, client, mock_userstore, mock_rolestore):
        mock_rolestore.ensure_default_role_for_user = AsyncMock(
            side_effect=Exception("role error")
        )
        service = _make_service(userstore=mock_userstore, rolestore=mock_rolestore)
        _wire(service)

        resp = await client.get("/api/users/")
        assert resp.status_code == 500

    async def test_get_users_error_500(self, client, mock_userstore, mock_rolestore):
        mock_userstore.get_users = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(userstore=mock_userstore, rolestore=mock_rolestore)
        _wire(service)

        resp = await client.get("/api/users/")
        assert resp.status_code == 500


# ===========================================================================
# POST /users/ — postUser
# ===========================================================================


class TestPostUser:
    async def test_sunny_day(self, client, mock_admin_userstore):
        mock_admin_userstore.add_user = AsyncMock(return_value=None)
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.post(
            "/api/users/",
            json={"email": "test@example.com", "firstName": "Test", "lastName": "User"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test@example.com"

    async def test_verify_failure_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.post(
            "/api/users/",
            json={"id": "x" * 37},  # too long
        )
        assert resp.status_code == 400

    async def test_add_user_error_500(self, client, mock_admin_userstore):
        mock_admin_userstore.add_user = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.post(
            "/api/users/",
            json={"email": "test@example.com"},
        )
        assert resp.status_code == 500


# ===========================================================================
# POST /users/{id}/role/{role} — postAddRole
# ===========================================================================


class TestPostAddRole:
    async def test_sunny_day(self, client, mock_admin_userstore):
        mock_admin_userstore.add_role = AsyncMock(return_value=None)
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.post(f"/api/users/{valid_id}/role/analyst")
        assert resp.status_code == 200

    async def test_invalid_id_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.post("/api/users/bad!id/role/analyst")
        assert resp.status_code == 400

    async def test_invalid_role_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.post(f"/api/users/{valid_id}/role/ab")  # too short
        assert resp.status_code == 400

    async def test_add_role_error_500(self, client, mock_admin_userstore):
        mock_admin_userstore.add_role = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.post(f"/api/users/{valid_id}/role/analyst")
        assert resp.status_code == 500


# ===========================================================================
# PUT /users/sync — putSync
# ===========================================================================


class TestPutSync:
    async def test_sunny_day(self, client, mock_admin_userstore):
        mock_admin_userstore.sync_users = AsyncMock(return_value=None)
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.put("/api/users/sync")
        assert resp.status_code == 200

    async def test_sync_error_500(self, client, mock_admin_userstore):
        mock_admin_userstore.sync_users = AsyncMock(side_effect=Exception("sync error"))
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.put("/api/users/sync")
        assert resp.status_code == 500


# ===========================================================================
# PUT /users/{id} — putUser
# ===========================================================================


class TestPutUser:
    async def test_sunny_day(self, client, mock_admin_userstore):
        mock_admin_userstore.update_profile = AsyncMock(return_value=None)
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.put(
            f"/api/users/{valid_id}",
            json={"email": "new@example.com", "firstName": "New", "lastName": "Name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == valid_id
        assert data["email"] == "new@example.com"

    async def test_verify_failure_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.put(
            f"/api/users/{valid_id}",
            json={"firstName": "x" * 101},  # too long
        )
        assert resp.status_code == 400

    async def test_update_error_500(self, client, mock_admin_userstore):
        mock_admin_userstore.update_profile = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.put(
            f"/api/users/{valid_id}",
            json={"email": "new@example.com"},
        )
        assert resp.status_code == 500


# ===========================================================================
# PUT /users/{id}/password — putPassword
# ===========================================================================


class TestPutPassword:
    async def test_sunny_day(self, client, mock_admin_userstore):
        mock_admin_userstore.reset_password = AsyncMock(return_value=None)
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.put(
            f"/api/users/{valid_id}/password",
            json={"password": "newpassword123"},
        )
        assert resp.status_code == 200

    async def test_invalid_id_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.put(
            "/api/users/bad!id/password",
            json={"password": "newpassword123"},
        )
        assert resp.status_code == 400

    async def test_reset_error_500(self, client, mock_admin_userstore):
        mock_admin_userstore.reset_password = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.put(
            f"/api/users/{valid_id}/password",
            json={"password": "newpassword123"},
        )
        assert resp.status_code == 500


# ===========================================================================
# PUT /users/{id}/{toggle} — putToggleUser
# ===========================================================================


class TestPutToggleUser:
    async def test_enable(self, client, mock_admin_userstore):
        mock_admin_userstore.enable_user = AsyncMock(return_value=None)
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.put(f"/api/users/{valid_id}/enable")
        assert resp.status_code == 200

    async def test_disable(self, client, mock_admin_userstore):
        mock_admin_userstore.disable_user = AsyncMock(return_value=None)
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.put(f"/api/users/{valid_id}/disable")
        assert resp.status_code == 200

    async def test_invalid_id_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.put("/api/users/bad!id/enable")
        assert resp.status_code == 400

    async def test_invalid_toggle_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.put(f"/api/users/{valid_id}/foobar")
        assert resp.status_code == 400

    async def test_enable_error_500(self, client, mock_admin_userstore):
        mock_admin_userstore.enable_user = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.put(f"/api/users/{valid_id}/enable")
        assert resp.status_code == 500


# ===========================================================================
# DELETE /users/{id} — deleteUser
# ===========================================================================


class TestDeleteUser:
    async def test_sunny_day(self, client, mock_admin_userstore):
        mock_admin_userstore.delete_user = AsyncMock(return_value=None)
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.delete(f"/api/users/{valid_id}")
        assert resp.status_code == 200

    async def test_invalid_id_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.delete("/api/users/bad!id")
        assert resp.status_code == 400

    async def test_delete_error_500(self, client, mock_admin_userstore):
        mock_admin_userstore.delete_user = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.delete(f"/api/users/{valid_id}")
        assert resp.status_code == 500


# ===========================================================================
# DELETE /users/{id}/role/{role} — deleteUserRole
# ===========================================================================


class TestDeleteUserRole:
    async def test_sunny_day(self, client, mock_admin_userstore):
        mock_admin_userstore.delete_role = AsyncMock(return_value=None)
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.delete(f"/api/users/{valid_id}/role/analyst")
        assert resp.status_code == 200

    async def test_invalid_id_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        resp = await client.delete("/api/users/bad!id/role/analyst")
        assert resp.status_code == 400

    async def test_invalid_role_400(self, client, mock_admin_userstore):
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.delete(f"/api/users/{valid_id}/role/ab")  # too short
        assert resp.status_code == 400

    async def test_delete_role_error_500(self, client, mock_admin_userstore):
        mock_admin_userstore.delete_role = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_userstore=mock_admin_userstore)
        _wire(service)

        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resp = await client.delete(f"/api/users/{valid_id}/role/analyst")
        assert resp.status_code == 500
