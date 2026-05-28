"""Tests for the /api/events/ routes — ported from Go eventhandler.go."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.events_routes import (
    get_events_service,
    get_request_context_dep,
    router as events_router,
)
from src.domain.event import (
    EventAckCriteria,
    EventSearchCriteria,
    EventSearchResults,
    EventUpdateResults,
)
from src.services.events_service import EventsService
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Fake Eventstore — stub for testing
# ---------------------------------------------------------------------------

class FakeEventstore:
    """In-memory stub implementing the Eventstore protocol for events tests."""

    def __init__(self) -> None:
        self.search_results = EventSearchResults()
        self.ack_results = EventUpdateResults()
        self.last_search_criteria: EventSearchCriteria | None = None
        self.last_ack_criteria: EventAckCriteria | None = None
        self.search_error: Exception | None = None
        self.ack_error: Exception | None = None

    async def search(
        self, criteria: EventSearchCriteria,
    ) -> EventSearchResults:
        if self.search_error:
            raise self.search_error
        self.last_search_criteria = criteria
        return self.search_results

    async def acknowledge(
        self, criteria: EventAckCriteria,
    ) -> EventUpdateResults:
        if self.ack_error:
            raise self.ack_error
        self.last_ack_criteria = criteria
        return self.ack_results

    async def get_active_queries(self, filter_internal: bool) -> list:
        return []

    async def cancel_query(self, query_id: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(
    fake_store: FakeEventstore, *, eventstore_configured: bool = True,
) -> FastAPI:
    """Build a fresh FastAPI app wired to the fake store."""
    test_app = FastAPI()
    test_app.include_router(events_router, prefix="/api")

    store = fake_store if eventstore_configured else None
    service = EventsService(eventstore=store)
    test_app.dependency_overrides[get_events_service] = lambda: service
    test_app.dependency_overrides[get_request_context_dep] = lambda: RequestContext(
        requestor_id="test-user-id",
        username="test",
    )
    return test_app


@pytest.fixture
def fake_store() -> FakeEventstore:
    return FakeEventstore()


@pytest.fixture
async def client(fake_store: FakeEventstore):
    test_app = _make_app(fake_store, eventstore_configured=True)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def disabled_client(fake_store: FakeEventstore):
    test_app = _make_app(fake_store, eventstore_configured=False)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# Middleware: 405 when eventstore not configured
# ===========================================================================

class TestEventsEnabled:
    async def test_search_returns_405_when_eventstore_not_configured(self, disabled_client):
        resp = await disabled_client.get("/api/events/")
        assert resp.status_code == 405

    async def test_ack_returns_405_when_eventstore_not_configured(self, disabled_client):
        resp = await disabled_client.post(
            "/api/events/ack",
            json={"searchFilter": "test"},
        )
        assert resp.status_code == 405


# ===========================================================================
# GET /events/ — search events
# ===========================================================================

class TestGetEvents:
    async def test_search_success(self, client, fake_store):
        fake_store.search_results.total_events = 5
        resp = await client.get(
            "/api/events/",
            params={
                "query": "*",
                "range": "2024/01/01 12:00:00 PM - 2024/01/02 12:00:00 PM",
                "zone": "UTC",
                "format": "%Y/%m/%d %I:%M:%S %p",
                "metricLimit": "10",
                "eventLimit": "25",
            },
        )
        assert resp.status_code == 200
        assert fake_store.last_search_criteria is not None

    async def test_search_bad_criteria(self, client):
        resp = await client.get(
            "/api/events/",
            params={
                "query": "*",
                "range": "2024/01/01 12:00:00 PM - 2024/01/02 12:00:00 PM",
                "zone": "UTC",
                "format": "%Y/%m/%d %I:%M:%S %p",
                "metricLimit": "not-a-number",
                "eventLimit": "25",
            },
        )
        assert resp.status_code == 400

    async def test_search_store_error(self, client, fake_store):
        fake_store.search_error = Exception("search failed")
        resp = await client.get(
            "/api/events/",
            params={
                "query": "*",
                "range": "2024/01/01 12:00:00 PM - 2024/01/02 12:00:00 PM",
                "zone": "UTC",
                "format": "%Y/%m/%d %I:%M:%S %p",
                "metricLimit": "10",
                "eventLimit": "25",
            },
        )
        assert resp.status_code == 500


# ===========================================================================
# POST /events/ack — acknowledge alerts
# ===========================================================================

class TestPostAck:
    async def test_ack_success(self, client, fake_store):
        fake_store.ack_results.updated_count = 3
        resp = await client.post(
            "/api/events/ack",
            json={
                "searchFilter": "alert.severity:high",
                "acknowledge": True,
            },
        )
        assert resp.status_code == 200
        assert fake_store.last_ack_criteria is not None

    async def test_ack_invalid_body(self, client):
        resp = await client.post(
            "/api/events/ack",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_ack_store_error(self, client, fake_store):
        fake_store.ack_error = Exception("ack failed")
        resp = await client.post(
            "/api/events/ack",
            json={
                "searchFilter": "test",
                "acknowledge": True,
            },
        )
        assert resp.status_code == 400
