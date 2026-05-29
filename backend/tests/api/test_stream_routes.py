"""Tests for the /api/stream/ routes — ported from Go server/streamhandler.go."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.stream_routes import get_stream_service
from src.api.stream_routes import router as stream_router
from src.services.stream_service import StreamService

# ---------------------------------------------------------------------------
# Fake Datastore — stub for testing
# ---------------------------------------------------------------------------

class FakeDatastore:
    """In-memory stub implementing the stream-related Datastore methods."""

    def __init__(self) -> None:
        self.saved_streams: list[tuple[int, bytes]] = []
        self.get_stream_calls: list[tuple[int, bool]] = []

        # Configurable return values
        self.stream_content: bytes | None = None
        self.stream_filename: str = "output.bin"
        self.stream_length: int = 0
        self.stream_mime_type: str = "application/octet-stream"
        self.get_error: Exception | None = None
        self.save_error: Exception | None = None

    async def get_job_stream(
        self, job_id: int, unwrap: bool,
    ) -> tuple[bytes | None, str, int, str]:
        self.get_stream_calls.append((job_id, unwrap))
        if self.get_error:
            raise self.get_error
        return (
            self.stream_content,
            self.stream_filename,
            self.stream_length,
            self.stream_mime_type,
        )

    async def save_job_stream(self, job_id: int, data: bytes) -> None:
        if self.save_error:
            raise self.save_error
        self.saved_streams.append((job_id, data))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(fake_store: FakeDatastore) -> FastAPI:
    """Build a fresh FastAPI app wired to the fake store."""
    test_app = FastAPI()
    test_app.include_router(stream_router, prefix="/api")

    service = StreamService(datastore=fake_store)
    test_app.dependency_overrides[get_stream_service] = lambda: service
    return test_app


@pytest.fixture
def fake_store() -> FakeDatastore:
    return FakeDatastore()


@pytest.fixture
async def client(fake_store: FakeDatastore):
    test_app = _make_app(fake_store)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# GET /stream/{jobId} — download job output
# ===========================================================================

class TestGetStream:
    async def test_get_stream_success(self, client, fake_store):
        fake_store.stream_content = b"\x89PNG\r\n\x1a\nfakeimage"
        fake_store.stream_filename = "capture.bin"
        fake_store.stream_length = 18
        fake_store.stream_mime_type = "vnd.tcpdump.pcap"

        resp = await client.get("/api/stream/1004")
        assert resp.status_code == 200
        assert resp.content == b"\x89PNG\r\n\x1a\nfakeimage"
        assert resp.headers["content-type"] == "vnd.tcpdump.pcap"
        assert resp.headers["content-disposition"] == 'inline; filename="capture.bin"'
        assert resp.headers["content-transfer-encoding"] == "binary"
        assert fake_store.get_stream_calls == [(1004, False)]

    async def test_get_stream_with_query_param_job_id(self, client, fake_store):
        fake_store.stream_content = b"data"
        fake_store.stream_filename = "output.bin"
        fake_store.stream_length = 4
        fake_store.stream_mime_type = "application/octet-stream"

        resp = await client.get("/api/stream/?jobId=42")
        assert resp.status_code == 200
        assert fake_store.get_stream_calls == [(42, False)]

    async def test_get_stream_with_unwrap(self, client, fake_store):
        fake_store.stream_content = b"data"
        fake_store.stream_filename = "output.bin"
        fake_store.stream_length = 4
        fake_store.stream_mime_type = "application/octet-stream"

        resp = await client.get("/api/stream/1004?unwrap=true")
        assert resp.status_code == 200
        assert fake_store.get_stream_calls == [(1004, True)]

    async def test_get_stream_with_ext(self, client, fake_store):
        fake_store.stream_content = b"pcapdata"
        fake_store.stream_filename = "capture.bin"
        fake_store.stream_length = 8
        fake_store.stream_mime_type = "vnd.tcpdump.pcap"

        resp = await client.get("/api/stream/1004?ext=pcap")
        assert resp.status_code == 200
        # .bin should be replaced with .pcap
        assert resp.headers["content-disposition"] == 'inline; filename="capture.pcap"'

    async def test_get_stream_ext_already_present(self, client, fake_store):
        fake_store.stream_content = b"data"
        fake_store.stream_filename = "capture.pcap"
        fake_store.stream_length = 4
        fake_store.stream_mime_type = "vnd.tcpdump.pcap"

        resp = await client.get("/api/stream/1004?ext=pcap")
        assert resp.status_code == 200
        # Already has .pcap, should not duplicate
        assert resp.headers["content-disposition"] == 'inline; filename="capture.pcap"'

    async def test_get_stream_invalid_ext(self, client, fake_store):
        fake_store.stream_content = b"data"
        fake_store.stream_filename = "output.bin"
        fake_store.stream_length = 4
        fake_store.stream_mime_type = "application/octet-stream"

        resp = await client.get("/api/stream/1004?ext=../bad")
        assert resp.status_code == 400

    async def test_get_stream_invalid_job_id(self, client):
        resp = await client.get("/api/stream/notanumber")
        assert resp.status_code == 400

    async def test_get_stream_no_job_id(self, client):
        resp = await client.get("/api/stream/")
        assert resp.status_code == 400

    async def test_get_stream_not_found(self, client, fake_store):
        fake_store.stream_content = None
        resp = await client.get("/api/stream/9999")
        assert resp.status_code == 404


# ===========================================================================
# POST /stream/{jobId} — upload job output
# ===========================================================================

class TestPostStream:
    async def test_post_stream_success(self, client, fake_store):
        data = b"binary pcap data here"
        resp = await client.post(
            "/api/stream/1004",
            content=data,
            headers={"content-type": "application/octet-stream"},
        )
        assert resp.status_code == 200
        assert len(fake_store.saved_streams) == 1
        assert fake_store.saved_streams[0] == (1004, data)

    async def test_post_stream_with_query_param_job_id(self, client, fake_store):
        data = b"data"
        resp = await client.post(
            "/api/stream/?jobId=42",
            content=data,
            headers={"content-type": "application/octet-stream"},
        )
        assert resp.status_code == 200
        assert fake_store.saved_streams[0] == (42, data)

    async def test_post_stream_invalid_job_id(self, client):
        resp = await client.post(
            "/api/stream/notanumber",
            content=b"data",
            headers={"content-type": "application/octet-stream"},
        )
        assert resp.status_code == 400

    async def test_post_stream_no_job_id(self, client):
        resp = await client.post(
            "/api/stream/",
            content=b"data",
            headers={"content-type": "application/octet-stream"},
        )
        assert resp.status_code == 400

    async def test_post_stream_not_found(self, client, fake_store):
        fake_store.save_error = ValueError("Job not found")
        resp = await client.post(
            "/api/stream/9999",
            content=b"data",
            headers={"content-type": "application/octet-stream"},
        )
        assert resp.status_code == 404

    async def test_post_stream_server_error(self, client, fake_store):
        fake_store.save_error = RuntimeError("disk full")
        resp = await client.post(
            "/api/stream/1004",
            content=b"data",
            headers={"content-type": "application/octet-stream"},
        )
        assert resp.status_code == 500
