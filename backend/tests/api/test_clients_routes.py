"""Tests for clients routes -- ported from Go clientshandler.go behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.domain.client import Client
from src.main import app
from src.api.clients_routes import get_clients_service, get_request_context_dep
from src.services.clients_service import ClientsService
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_context() -> RequestContext:
    return RequestContext(requestor_id="test-user-id", username="tester")


def _make_service(
    clientstore: Any = None,
    admin_clientstore: Any = None,
) -> ClientsService:
    if clientstore is None:
        clientstore = AsyncMock()
    if admin_clientstore is None:
        admin_clientstore = AsyncMock()
    return ClientsService(
        clientstore=clientstore,
        admin_clientstore=admin_clientstore,
    )


@pytest.fixture
def mock_clientstore():
    return AsyncMock()


@pytest.fixture
def mock_admin_clientstore():
    return AsyncMock()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _wire(service: ClientsService) -> None:
    app.dependency_overrides[get_clients_service] = lambda: service
    app.dependency_overrides[get_request_context_dep] = _fake_context


# ===========================================================================
# GET /clients/ — getClients
# ===========================================================================


class TestGetClients:
    async def test_sunny_day(self, client, mock_clientstore):
        clients = [
            Client(id="socl_client1", name="Client 1"),
            Client(id="socl_client2", name="Client 2"),
        ]
        mock_clientstore.get_clients = AsyncMock(return_value=clients)
        service = _make_service(clientstore=mock_clientstore)
        _wire(service)

        resp = await client.get("/api/clients/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "socl_client1"

    async def test_get_clients_error_400(self, client, mock_clientstore):
        mock_clientstore.get_clients = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(clientstore=mock_clientstore)
        _wire(service)

        resp = await client.get("/api/clients/")
        assert resp.status_code == 400


# ===========================================================================
# POST /clients/ — postClient
# ===========================================================================


class TestPostClient:
    async def test_sunny_day(self, client, mock_admin_clientstore):
        new_client = Client(id="socl_new_client", name="New", secret="secret123")
        mock_admin_clientstore.add_client = AsyncMock(return_value=new_client)
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.post(
            "/api/clients/",
            json={"name": "New", "note": "A test client"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "socl_new_client"
        assert data["secret"] == "secret123"

    async def test_verify_failure_400(self, client, mock_admin_clientstore):
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.post(
            "/api/clients/",
            json={"id": "x" * 56},  # too long
        )
        assert resp.status_code == 400

    async def test_add_client_error_500(self, client, mock_admin_clientstore):
        mock_admin_clientstore.add_client = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.post(
            "/api/clients/",
            json={"name": "New"},
        )
        assert resp.status_code == 500


# ===========================================================================
# POST /clients/{id}/permission/{resource}/{privilege} — postAddPermission
# ===========================================================================


class TestPostAddPermission:
    async def test_sunny_day(self, client, mock_admin_clientstore):
        mock_admin_clientstore.add_client_permission = AsyncMock(return_value=None)
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.post("/api/clients/socl_my_client/permission/events/read")
        assert resp.status_code == 200

    async def test_invalid_client_id_400(self, client, mock_admin_clientstore):
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.post("/api/clients/bad!/permission/events/read")
        assert resp.status_code == 400

    async def test_invalid_permission_format_400(self, client, mock_admin_clientstore):
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.post("/api/clients/socl_my_client/permission/EVENTS/READ")
        assert resp.status_code == 400

    async def test_add_permission_error_500(self, client, mock_admin_clientstore):
        mock_admin_clientstore.add_client_permission = AsyncMock(
            side_effect=Exception("db error")
        )
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.post("/api/clients/socl_my_client/permission/events/read")
        assert resp.status_code == 500


# ===========================================================================
# PUT /clients/{id} — putClient
# ===========================================================================


class TestPutClient:
    async def test_sunny_day(self, client, mock_admin_clientstore):
        mock_admin_clientstore.update_client = AsyncMock(return_value=None)
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.put(
            "/api/clients/socl_my_client",
            json={"name": "Updated Name", "note": "Updated note"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "socl_my_client"
        assert data["name"] == "Updated Name"

    async def test_invalid_client_id_400(self, client, mock_admin_clientstore):
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.put(
            "/api/clients/bad!",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 400

    async def test_verify_failure_400(self, client, mock_admin_clientstore):
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.put(
            "/api/clients/socl_my_client",
            json={"name": "x" * 51},  # too long
        )
        assert resp.status_code == 400

    async def test_update_error_500(self, client, mock_admin_clientstore):
        mock_admin_clientstore.update_client = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.put(
            "/api/clients/socl_my_client",
            json={"name": "Updated"},
        )
        assert resp.status_code == 500


# ===========================================================================
# PUT /clients/{id}/secret — putGeneratedSecret
# ===========================================================================


class TestPutGeneratedSecret:
    async def test_sunny_day(self, client, mock_admin_clientstore):
        updated = Client(id="socl_my_client", name="My Client", secret="newsecret")
        mock_admin_clientstore.generate_secret = AsyncMock(return_value=updated)
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.put("/api/clients/socl_my_client/secret")
        assert resp.status_code == 200
        data = resp.json()
        assert data["secret"] == "newsecret"

    async def test_invalid_client_id_400(self, client, mock_admin_clientstore):
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.put("/api/clients/bad!/secret")
        assert resp.status_code == 400

    async def test_generate_error_500(self, client, mock_admin_clientstore):
        mock_admin_clientstore.generate_secret = AsyncMock(
            side_effect=Exception("db error")
        )
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.put("/api/clients/socl_my_client/secret")
        assert resp.status_code == 500


# ===========================================================================
# DELETE /clients/{id} — deleteClient
# ===========================================================================


class TestDeleteClient:
    async def test_sunny_day(self, client, mock_admin_clientstore):
        mock_admin_clientstore.delete_client = AsyncMock(return_value=None)
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.delete("/api/clients/socl_my_client")
        assert resp.status_code == 200

    async def test_invalid_client_id_400(self, client, mock_admin_clientstore):
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.delete("/api/clients/bad!")
        assert resp.status_code == 400

    async def test_delete_error_500(self, client, mock_admin_clientstore):
        mock_admin_clientstore.delete_client = AsyncMock(side_effect=Exception("db error"))
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.delete("/api/clients/socl_my_client")
        assert resp.status_code == 500


# ===========================================================================
# DELETE /clients/{id}/permission/{resource}/{privilege} — deleteClientPermission
# ===========================================================================


class TestDeleteClientPermission:
    async def test_sunny_day(self, client, mock_admin_clientstore):
        mock_admin_clientstore.delete_client_permission = AsyncMock(return_value=None)
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.delete("/api/clients/socl_my_client/permission/events/read")
        assert resp.status_code == 200

    async def test_invalid_client_id_400(self, client, mock_admin_clientstore):
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.delete("/api/clients/bad!/permission/events/read")
        assert resp.status_code == 400

    async def test_invalid_permission_format_400(self, client, mock_admin_clientstore):
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.delete("/api/clients/socl_my_client/permission/EVENTS/READ")
        assert resp.status_code == 400

    async def test_delete_permission_error_500(self, client, mock_admin_clientstore):
        mock_admin_clientstore.delete_client_permission = AsyncMock(
            side_effect=Exception("db error")
        )
        service = _make_service(admin_clientstore=mock_admin_clientstore)
        _wire(service)

        resp = await client.delete("/api/clients/socl_my_client/permission/events/read")
        assert resp.status_code == 500
