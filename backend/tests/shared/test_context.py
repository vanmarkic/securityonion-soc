"""Tests for RequestContext and auth middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.shared.context import AGENT_ID, SYSTEM_ID, RequestContext
from src.shared.middleware import get_request_context


class TestRequestContext:
    def test_create_context(self):
        ctx = RequestContext(requestor_id="user-1", username="alice")
        assert ctx.requestor_id == "user-1"
        assert ctx.username == "alice"

    def test_system_context(self):
        ctx = RequestContext.system()
        assert ctx.requestor_id == SYSTEM_ID
        assert ctx.username == "system"

    def test_agent_context(self):
        ctx = RequestContext.agent()
        assert ctx.requestor_id == AGENT_ID
        assert ctx.username == "agent"

    def test_system_id_constant(self):
        assert SYSTEM_ID == "00000000-0000-0000-0000-000000000000"

    def test_agent_id_constant(self):
        assert AGENT_ID == "00000000-0000-0000-0000-000000000001"


class TestGetRequestContext:
    def test_extracts_from_headers(self):
        """The middleware should extract user info from request headers."""
        app = FastAPI()

        @app.get("/test")
        async def test_route(ctx: RequestContext = pytest.importorskip("fastapi").Depends(get_request_context)):
            return {"requestor_id": ctx.requestor_id, "username": ctx.username}

        client = TestClient(app)
        resp = client.get(
            "/test",
            headers={"X-User-Id": "user-42", "X-Username": "bob"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["requestor_id"] == "user-42"
        assert data["username"] == "bob"

    def test_defaults_when_no_headers(self):
        """Without auth headers, should default to agent context."""
        app = FastAPI()

        @app.get("/test")
        async def test_route(ctx: RequestContext = pytest.importorskip("fastapi").Depends(get_request_context)):
            return {"requestor_id": ctx.requestor_id, "username": ctx.username}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["requestor_id"] == AGENT_ID
        assert data["username"] == "agent"
