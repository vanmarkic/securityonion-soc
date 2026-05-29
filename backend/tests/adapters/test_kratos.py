"""Tests for Kratos adapter — unit tests with mocked HTTP."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.adapters.kratos.userstore import KratosUserstore


def _make_kratos_identity(
    *,
    identity_id: str = "user-1",
    email: str = "user@test.local",
    first_name: str = "Test",
    last_name: str = "User",
    state: str = "active",
) -> dict:
    return {
        "id": identity_id,
        "schema_id": "default",
        "state": state,
        "traits": {
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
        },
        "verifiable_addresses": [
            {"id": "addr-1", "value": email, "verified": True, "via": "email"}
        ],
        "credentials": {},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


def _ok_response(payload) -> MagicMock:
    """A synchronous-style httpx.Response mock (json/raise_for_status are sync)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def mock_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def store(mock_client: AsyncMock) -> KratosUserstore:
    s = KratosUserstore(host_url="http://kratos:4434")
    s._client = mock_client
    return s


class TestGetUsers:
    async def test_returns_mapped_users(self, store: KratosUserstore, mock_client: AsyncMock):
        mock_client.get.return_value = _ok_response([
            _make_kratos_identity(identity_id="u1", email="a@test.local"),
            _make_kratos_identity(identity_id="u2", email="b@test.local"),
        ])
        users = await store.get_users()
        assert len(users) == 2
        assert users[0].id == "u1"
        assert users[0].email == "a@test.local"
        assert users[0].first_name == "Test"
        assert users[1].id == "u2"

    async def test_inactive_user_status_locked(self, store: KratosUserstore, mock_client: AsyncMock):
        mock_client.get.return_value = _ok_response([_make_kratos_identity(state="inactive")])
        users = await store.get_users()
        assert users[0].status == "locked"

    async def test_active_user_status_empty(self, store: KratosUserstore, mock_client: AsyncMock):
        mock_client.get.return_value = _ok_response([_make_kratos_identity(state="active")])
        users = await store.get_users()
        assert users[0].status == ""


class TestGetUserById:
    async def test_returns_user(self, store: KratosUserstore, mock_client: AsyncMock):
        mock_client.get.return_value = _ok_response(
            _make_kratos_identity(identity_id="u1", email="a@test.local")
        )
        user = await store.get_user_by_id("u1")
        assert user is not None
        assert user.id == "u1"
        assert user.email == "a@test.local"

    async def test_not_found_returns_none(self, store: KratosUserstore, mock_client: AsyncMock):
        resp = MagicMock()
        resp.status_code = 404
        request = httpx.Request("GET", "http://kratos:4434/identities/nonexistent")
        response = httpx.Response(404, request=request)
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=request, response=response
        )
        mock_client.get.return_value = resp
        user = await store.get_user_by_id("nonexistent")
        assert user is None

    async def test_server_error_propagates(self, store: KratosUserstore, mock_client: AsyncMock):
        resp = MagicMock()
        resp.status_code = 500
        request = httpx.Request("GET", "http://kratos:4434/identities/u1")
        response = httpx.Response(500, request=request)
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=request, response=response
        )
        mock_client.get.return_value = resp
        with pytest.raises(httpx.HTTPStatusError):
            await store.get_user_by_id("u1")


class TestCredentialMapping:
    async def test_totp_enabled(self, store: KratosUserstore, mock_client: AsyncMock):
        identity = _make_kratos_identity()
        identity["credentials"] = {
            "totp": {"created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"}
        }
        mock_client.get.return_value = _ok_response([identity])
        users = await store.get_users()
        assert users[0].totp_status == "enabled"

    async def test_webauthn_enabled(self, store: KratosUserstore, mock_client: AsyncMock):
        identity = _make_kratos_identity()
        identity["credentials"] = {
            "webauthn": {"created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"}
        }
        mock_client.get.return_value = _ok_response([identity])
        users = await store.get_users()
        assert users[0].webauthn_status == "enabled"

    async def test_no_credentials_empty_status(self, store: KratosUserstore, mock_client: AsyncMock):
        mock_client.get.return_value = _ok_response([_make_kratos_identity()])
        users = await store.get_users()
        assert users[0].totp_status == ""
        assert users[0].webauthn_status == ""
