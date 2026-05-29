"""Tests for the /api/query/ routes — ported from Go queryhandler_test.go."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.query_routes import (
    get_query_service,
    get_request_context_dep,
)
from src.api.query_routes import (
    router as query_router,
)
from src.domain.event import EventSearchCriteria, EventSearchResults
from src.ports.events import QueryTask
from src.services.query_service import QueryNotFoundError, QueryService
from src.shared.context import RequestContext

# ---------------------------------------------------------------------------
# Fake Eventstore — stub for testing
# ---------------------------------------------------------------------------

class FakeEventstore:
    """In-memory stub implementing the Eventstore protocol for tests."""

    def __init__(self) -> None:
        self.queries: list[QueryTask] = [
            QueryTask(task_id="1", details="test query 1"),
            QueryTask(task_id="2", details="test query 2"),
        ]
        self.cancel_error: Exception | None = None

    async def search(
        self, criteria: EventSearchCriteria,
    ) -> EventSearchResults:
        return EventSearchResults()

    async def get_active_queries(
        self, filter_internal: bool,
    ) -> list[QueryTask]:
        return self.queries

    async def cancel_query(self, query_id: str) -> None:
        if query_id == "notFound":
            raise QueryNotFoundError("query not found")
        elif query_id == "error":
            raise Exception("some error")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(*, licensed: bool = True) -> tuple[FastAPI, FakeEventstore]:
    """Build a fresh FastAPI app wired to the fake store."""
    fake_store = FakeEventstore()
    test_app = FastAPI()
    test_app.include_router(query_router, prefix="/api")

    service = QueryService(eventstore=fake_store, licensed=licensed)
    test_app.dependency_overrides[get_query_service] = lambda: service
    test_app.dependency_overrides[get_request_context_dep] = lambda: RequestContext(
        requestor_id="test-user-id",
        username="test",
    )
    return test_app, fake_store


@pytest.fixture
async def client():
    test_app, _ = _make_app(licensed=True)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def unlicensed_client():
    test_app, _ = _make_app(licensed=False)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# GET /query/filtered — TestFilterMissing (from Go)
# ===========================================================================

class TestFilterMissing:
    """Ported from Go TestFilterMissing — tests __missing__ value handling."""

    async def test_filter_include_missing(self, client):
        resp = await client.get(
            "/api/query/filtered",
            params={
                "query": "* | groupby unit.type*",
                "field": "unit.type",
                "value": "__missing__",
                "scalar": "false",
                "mode": "INCLUDE",
            },
        )
        assert resp.status_code == 200
        expected = '"* AND NOT _exists_:\\"unit.type\\" | groupby unit.type*"'
        assert resp.text == expected

    async def test_filter_exclude_missing(self, client):
        resp = await client.get(
            "/api/query/filtered",
            params={
                "query": "* | groupby unit.type*",
                "field": "unit.type",
                "value": "__missing__",
                "scalar": "false",
                "mode": "EXCLUDE",
            },
        )
        assert resp.status_code == 200
        expected = '"* AND _exists_:\\"unit.type\\" | groupby unit.type*"'
        assert resp.text == expected

    async def test_filter_drilldown_missing(self, client):
        resp = await client.get(
            "/api/query/filtered",
            params={
                "query": "* | groupby unit.type*",
                "field": "unit.type",
                "value": "__missing__",
                "scalar": "false",
                "mode": "DRILLDOWN",
            },
        )
        assert resp.status_code == 200
        expected = '"* AND NOT _exists_:\\"unit.type\\""'
        assert resp.text == expected


# ===========================================================================
# GET /query/active — TestGetActiveQueries (from Go)
# ===========================================================================

class TestGetActiveQueries:
    async def test_get_active_queries_no_license(self, unlicensed_client):
        """Ported from Go TestGetActiveQueriesNoLicense."""
        resp = await unlicensed_client.get("/api/query/active")
        assert resp.status_code == 400
        assert resp.text == "ERROR_LICENSE_INVALID"

    async def test_get_active_queries_success(self, client):
        """Ported from Go TestGetActiveQueries."""
        resp = await client.get("/api/query/active")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["taskId"] == "1"
        assert data[0]["details"] == "test query 1"
        assert data[0]["gridId"] == ""
        assert data[0]["startTime"] == "0001-01-01T00:00:00Z"
        assert data[0]["elapsedMs"] == 0
        assert data[0]["cancelable"] is False
        assert data[1]["taskId"] == "2"
        assert data[1]["details"] == "test query 2"


# ===========================================================================
# POST /query/cancel/{queryId} — TestPostCancelQuery* (from Go)
# ===========================================================================

class TestPostCancelQuery:
    async def test_cancel_query_no_license(self, unlicensed_client):
        """Ported from Go TestPostCancelQueryNoLicense."""
        resp = await unlicensed_client.post("/api/query/cancel/123")
        assert resp.status_code == 400
        assert resp.text == "ERROR_LICENSE_INVALID"

    async def test_cancel_query_not_found(self, client):
        """Ported from Go TestPostCancelQueryNotFound."""
        resp = await client.post("/api/query/cancel/notFound")
        assert resp.status_code == 404
        assert resp.text == "ERROR_QUERY_NOT_FOUND"

    async def test_cancel_query_success(self, client):
        """Ported from Go TestPostCancelQuerySuccess."""
        resp = await client.post("/api/query/cancel/success")
        assert resp.status_code == 200
        assert resp.text == ""

    async def test_cancel_query_error(self, client):
        """Ported from Go TestPostCancelQueryError."""
        resp = await client.post("/api/query/cancel/error")
        assert resp.status_code == 400
        assert resp.text == "The request could not be processed."
