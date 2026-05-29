"""Tests for StaticKeyAuth adapter — ported from Go statickeyauthimpl_test.go."""

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.adapters.statickeyauth.middleware import StaticKeyAuth
from src.shared.context import AGENT_ID, RequestContext


class TestValidateApiKey:
    """Ported from Go TestValidateApiKey."""

    @pytest.fixture
    def auth(self) -> StaticKeyAuth:
        ska = StaticKeyAuth(api_key="abc", anonymous_cidr="0.0.0.0/0")
        return ska

    def test_empty_key_rejected(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("") is False

    def test_wrong_prefix_rejected(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("basic xyz") is False

    def test_wrong_single_token_rejected(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("basic") is False

    def test_exact_key_accepted(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("abc") is True

    def test_prefixed_key_accepted(self, auth: StaticKeyAuth):
        assert auth.validate_api_key("basic abc") is True


class TestValidateAuthorization:
    """Ported from Go TestValidateAuthorization."""

    def _make(self, cidr: str) -> StaticKeyAuth:
        return StaticKeyAuth(api_key="abc", anonymous_cidr=cidr)

    def test_correct_key_any_ip(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("abc", "1.1.1.1") is True

    def test_wrong_key_outside_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("a", "1.1.1.1") is False

    def test_no_key_outside_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("", "1.1.1.1") is False

    def test_no_key_outside_cidr_close(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("", "172.17.1.1") is False

    def test_no_key_inside_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("", "172.17.0.1") is True

    def test_correct_key_inside_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("abc", "172.17.0.1") is True

    def test_wildcard_no_key(self):
        auth = self._make("*")
        assert auth.validate_authorization("", "1.1.1.1") is True

    def test_wildcard_correct_key(self):
        auth = self._make("*")
        assert auth.validate_authorization("abc", "1.1.1.1") is True

    def test_wildcard_wrong_key(self):
        auth = self._make("*")
        assert auth.validate_authorization("abcd", "1.1.1.1") is False

    def test_bearer_prefix_falls_through_to_cidr(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("Bearer token123", "172.17.0.1") is True

    def test_bearer_prefix_outside_cidr_rejected(self):
        auth = self._make("172.17.0.0/24")
        assert auth.validate_authorization("Bearer token123", "1.1.1.1") is False


class TestInit:
    """Ported from Go TestAuthImplInit."""

    def test_invalid_cidr_raises(self):
        with pytest.raises(ValueError):
            StaticKeyAuth(api_key="abc", anonymous_cidr="1")

    def test_valid_cidr_parses(self):
        auth = StaticKeyAuth(api_key="abc", anonymous_cidr="1.2.3.4/16")
        assert auth.api_key == "abc"
        assert auth.anonymous_cidr == "1.2.3.4/16"

    def test_wildcard_accepted(self):
        auth = StaticKeyAuth(api_key="abc", anonymous_cidr="*")
        assert auth._skip_cidr_check is True


class TestCall:
    """Exercises the FastAPI dependency (__call__) — the security boundary."""

    def _make_app(self, auth: StaticKeyAuth) -> FastAPI:
        app = FastAPI()

        @app.get("/whoami")
        async def whoami(ctx: RequestContext = Depends(auth)) -> dict[str, str]:
            return {"requestor_id": ctx.requestor_id}

        return app

    async def test_valid_api_key_succeeds(self):
        auth = StaticKeyAuth(api_key="abc", anonymous_cidr="172.17.0.0/24")
        app = self._make_app(auth)
        transport = ASGITransport(app=app, client=("1.1.1.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/whoami", headers={"Authorization": "abc"})
        assert resp.status_code == 200
        assert resp.json()["requestor_id"] == AGENT_ID

    async def test_wrong_key_outside_cidr_rejected(self):
        auth = StaticKeyAuth(api_key="abc", anonymous_cidr="172.17.0.0/24")
        app = self._make_app(auth)
        transport = ASGITransport(app=app, client=("1.1.1.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/whoami", headers={"Authorization": "wrong"})
        assert resp.status_code == 401

    async def test_no_key_wildcard_cidr_succeeds(self):
        auth = StaticKeyAuth(api_key="abc", anonymous_cidr="*")
        app = self._make_app(auth)
        transport = ASGITransport(app=app, client=("1.1.1.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/whoami")
        assert resp.status_code == 200
        assert resp.json()["requestor_id"] == AGENT_ID
