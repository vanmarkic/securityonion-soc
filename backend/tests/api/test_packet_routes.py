"""Tests for the /api/packets/ routes — ported from Go packethandler.go."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.packet_routes import (
    get_packet_service,
    get_request_context_dep,
    router as packet_router,
)
from src.services.packet_service import PacketService
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Fake PacketDatastore — stub for testing
# ---------------------------------------------------------------------------

class FakePacketDatastore:
    """In-memory stub implementing the PacketDatastore protocol for tests."""

    def __init__(self) -> None:
        self.packets_to_return: list[dict[str, Any]] = []
        self.get_error: Exception | None = None
        self.last_job_id: int | None = None
        self.last_offset: int | None = None
        self.last_count: int | None = None
        self.last_unwrap: bool | None = None

    async def get_packets(
        self, job_id: int, offset: int, count: int, unwrap: bool,
    ) -> list[dict[str, Any]]:
        if self.get_error:
            raise self.get_error
        self.last_job_id = job_id
        self.last_offset = offset
        self.last_count = count
        self.last_unwrap = unwrap
        return self.packets_to_return


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(
    fake_store: FakePacketDatastore, *, max_packet_count: int = 5000,
) -> FastAPI:
    """Build a fresh FastAPI app wired to the fake store."""
    test_app = FastAPI()
    test_app.include_router(packet_router, prefix="/api")

    service = PacketService(
        datastore=fake_store, max_packet_count=max_packet_count,
    )
    test_app.dependency_overrides[get_packet_service] = lambda: service
    test_app.dependency_overrides[get_request_context_dep] = lambda: RequestContext(
        requestor_id="test-user-id",
        username="test",
    )
    return test_app


@pytest.fixture
def fake_store() -> FakePacketDatastore:
    return FakePacketDatastore()


@pytest.fixture
async def client(fake_store: FakePacketDatastore):
    test_app = _make_app(fake_store)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# GET /packets/{jobId} — get packets by path param
# ===========================================================================

class TestGetPacketsByPath:
    async def test_get_packets_success(self, client, fake_store):
        fake_store.packets_to_return = [
            {"number": 0, "type": "TCP", "srcIp": "1.2.3.4"},
            {"number": 1, "type": "UDP", "srcIp": "5.6.7.8"},
        ]
        resp = await client.get("/api/packets/1004")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["number"] == 0
        assert data[1]["type"] == "UDP"
        assert fake_store.last_job_id == 1004
        assert fake_store.last_offset == 0
        assert fake_store.last_count == 5000
        assert fake_store.last_unwrap is False

    async def test_get_packets_with_params(self, client, fake_store):
        fake_store.packets_to_return = []
        resp = await client.get(
            "/api/packets/1004",
            params={"unwrap": "true", "offset": "10", "count": "50"},
        )
        assert resp.status_code == 200
        assert fake_store.last_unwrap is True
        assert fake_store.last_offset == 10
        assert fake_store.last_count == 50

    async def test_get_packets_count_capped_at_max(self, client, fake_store):
        """Count requested > max_packet_count should use max_packet_count."""
        fake_store.packets_to_return = []
        resp = await client.get(
            "/api/packets/1004",
            params={"count": "99999"},
        )
        assert resp.status_code == 200
        # Should be capped at the server max (5000)
        assert fake_store.last_count == 5000

    async def test_get_packets_invalid_id(self, client):
        resp = await client.get("/api/packets/abc")
        assert resp.status_code == 400

    async def test_get_packets_store_error(self, client, fake_store):
        fake_store.get_error = Exception("not found")
        resp = await client.get("/api/packets/1004")
        assert resp.status_code == 404


# ===========================================================================
# GET /packets/?jobId= — get packets by query param
# ===========================================================================

class TestGetPacketsByQuery:
    async def test_get_packets_by_query_success(self, client, fake_store):
        fake_store.packets_to_return = [
            {"number": 0, "type": "DNS"},
        ]
        resp = await client.get("/api/packets/", params={"jobId": "1005"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert fake_store.last_job_id == 1005

    async def test_get_packets_by_query_invalid_id(self, client):
        resp = await client.get("/api/packets/", params={"jobId": "bad"})
        assert resp.status_code == 400

    async def test_get_packets_by_query_missing_id(self, client):
        resp = await client.get("/api/packets/")
        assert resp.status_code == 400
