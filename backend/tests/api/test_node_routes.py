"""Tests for the /api/node/ routes — ported from Go nodehandler.go."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.node_routes import (
    get_node_service,
    get_request_context_dep,
    router as node_router,
)
from src.domain.job import Job
from src.domain.node import Node
from src.services.node_service import NodeService
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Fake NodeDatastore — stub for testing
# ---------------------------------------------------------------------------

class FakeNodeDatastore:
    """In-memory stub implementing the NodeDatastore protocol for tests."""

    def __init__(self) -> None:
        self.updated_nodes: list[Node] = []
        self.update_error: Exception | None = None
        self.next_job: Job | None = None

    async def update_node(self, node: Node) -> Node:
        if self.update_error:
            raise self.update_error
        self.updated_nodes.append(node)
        return node

    def get_next_job(self, node_id: str) -> Job | None:
        return self.next_job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(fake_store: FakeNodeDatastore) -> FastAPI:
    """Build a fresh FastAPI app wired to the fake store."""
    test_app = FastAPI()
    test_app.include_router(node_router, prefix="/api")

    service = NodeService(datastore=fake_store)
    test_app.dependency_overrides[get_node_service] = lambda: service
    test_app.dependency_overrides[get_request_context_dep] = lambda: RequestContext(
        requestor_id="test-user-id",
        username="test",
    )
    return test_app


@pytest.fixture
def fake_store() -> FakeNodeDatastore:
    return FakeNodeDatastore()


@pytest.fixture
async def client(fake_store: FakeNodeDatastore):
    test_app = _make_app(fake_store)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# POST /node/ — node check-in
# ===========================================================================

class TestPostNode:
    async def test_checkin_success_no_pending_job(self, client, fake_store):
        """Node checks in, no pending jobs — returns null job."""
        resp = await client.post(
            "/api/node/",
            json={"id": "node-1", "role": "so-standalone", "status": "ok"},
        )
        assert resp.status_code == 200
        # When no pending job, response should be null
        assert resp.json() is None
        assert len(fake_store.updated_nodes) == 1
        assert fake_store.updated_nodes[0].id == "node-1"

    async def test_checkin_success_with_pending_job(self, client, fake_store):
        """Node checks in, there is a pending job — returns the job."""
        fake_store.next_job = Job(id=1001, kind="pcap", node_id="node-1")
        resp = await client.post(
            "/api/node/",
            json={"id": "node-1", "role": "so-sensor"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1001
        assert data["kind"] == "pcap"

    async def test_checkin_invalid_body(self, client):
        resp = await client.post(
            "/api/node/",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_checkin_store_error(self, client, fake_store):
        fake_store.update_error = Exception("db error")
        resp = await client.post(
            "/api/node/",
            json={"id": "node-1"},
        )
        assert resp.status_code == 500
