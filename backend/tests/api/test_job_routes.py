"""Tests for the /api/job/ routes — ported from Go jobhandler.go."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.job_routes import (
    get_job_service,
    get_request_context_dep,
    router as job_router,
)
from src.domain.job import Job
from src.services.job_service import JobService
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Fake JobDatastore — stub for testing
# ---------------------------------------------------------------------------

class FakeJobDatastore:
    """In-memory stub implementing the JobDatastore protocol for tests."""

    def __init__(self) -> None:
        self.jobs: dict[int, Job] = {}
        self.added_jobs: list[Job] = []
        self.updated_jobs: list[Job] = []
        self.deleted_ids: list[int] = []
        self.add_error: Exception | None = None
        self.update_error: Exception | None = None
        self.delete_error: str | None = None
        self.next_id: int = 1001

    def create_job(self) -> Job:
        job = Job()
        job.id = self.next_id
        self.next_id += 1
        return job

    def get_job(self, job_id: int) -> Job | None:
        return self.jobs.get(job_id)

    def get_jobs(self, kind: str, parameters: dict[str, Any]) -> list[Job]:
        return list(self.jobs.values())

    async def add_job(self, job: Job) -> None:
        if self.add_error:
            raise self.add_error
        self.added_jobs.append(job)

    async def update_job(self, job: Job) -> None:
        if self.update_error:
            raise self.update_error
        self.updated_jobs.append(job)

    async def delete_job(self, job_id: int) -> tuple[Job | None, str | None]:
        if self.delete_error:
            return None, self.delete_error
        self.deleted_ids.append(job_id)
        job = self.jobs.get(job_id)
        return job, None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(fake_store: FakeJobDatastore) -> FastAPI:
    """Build a fresh FastAPI app wired to the fake store."""
    test_app = FastAPI()
    test_app.include_router(job_router, prefix="/api")

    service = JobService(datastore=fake_store)
    test_app.dependency_overrides[get_job_service] = lambda: service
    test_app.dependency_overrides[get_request_context_dep] = lambda: RequestContext(
        requestor_id="test-user-id",
        username="test",
    )
    return test_app


@pytest.fixture
def fake_store() -> FakeJobDatastore:
    return FakeJobDatastore()


@pytest.fixture
async def client(fake_store: FakeJobDatastore):
    test_app = _make_app(fake_store)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# GET /job/{jobId} — getJob by path
# ===========================================================================

class TestGetJob:
    async def test_get_job_success(self, client, fake_store):
        fake_store.jobs[1004] = Job(id=1004, kind="pcap", node_id="node-1")
        resp = await client.get("/api/job/1004")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1004
        assert data["kind"] == "pcap"

    async def test_get_job_not_found(self, client):
        resp = await client.get("/api/job/9999")
        assert resp.status_code == 404

    async def test_get_job_invalid_id(self, client):
        resp = await client.get("/api/job/abc")
        assert resp.status_code == 400


# ===========================================================================
# GET /job/?jobId= — getJob by query param
# ===========================================================================

class TestGetJobByQuery:
    async def test_get_job_by_query_success(self, client, fake_store):
        fake_store.jobs[1005] = Job(id=1005, kind="analyze")
        resp = await client.get("/api/job/", params={"jobId": "1005"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1005

    async def test_get_job_by_query_not_found(self, client):
        resp = await client.get("/api/job/", params={"jobId": "9999"})
        assert resp.status_code == 404

    async def test_get_job_by_query_invalid_id(self, client):
        resp = await client.get("/api/job/", params={"jobId": "bad"})
        assert resp.status_code == 400


# ===========================================================================
# POST /job/ — createJob
# ===========================================================================

class TestPostJob:
    async def test_create_job_success(self, client, fake_store):
        resp = await client.post(
            "/api/job/",
            json={"kind": "pcap", "nodeId": "node-1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == 1001
        assert len(fake_store.added_jobs) == 1

    async def test_create_job_invalid_body(self, client):
        resp = await client.post(
            "/api/job/",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_create_job_store_error(self, client, fake_store):
        fake_store.add_error = Exception("db error")
        resp = await client.post(
            "/api/job/",
            json={"kind": "pcap"},
        )
        assert resp.status_code == 400


# ===========================================================================
# PUT /job/ — updateJob
# ===========================================================================

class TestPutJob:
    async def test_update_job_success(self, client, fake_store):
        resp = await client.put(
            "/api/job/",
            json={"id": 1004, "kind": "pcap", "status": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1004
        assert len(fake_store.updated_jobs) == 1

    async def test_update_job_store_error(self, client, fake_store):
        fake_store.update_error = Exception("update failed")
        resp = await client.put(
            "/api/job/",
            json={"id": 1004, "kind": "pcap"},
        )
        assert resp.status_code == 404


# ===========================================================================
# DELETE /job/{jobId} — deleteJob
# ===========================================================================

class TestDeleteJob:
    async def test_delete_job_success(self, client, fake_store):
        fake_store.jobs[1004] = Job(id=1004)
        resp = await client.delete("/api/job/1004")
        assert resp.status_code == 200
        assert 1004 in fake_store.deleted_ids

    async def test_delete_job_invalid_id(self, client):
        resp = await client.delete("/api/job/abc")
        assert resp.status_code == 400

    async def test_delete_job_store_error(self, client, fake_store):
        fake_store.delete_error = "delete failed"
        resp = await client.delete("/api/job/1004")
        assert resp.status_code == 500
