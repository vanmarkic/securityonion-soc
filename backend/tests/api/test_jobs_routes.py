"""Tests for the /api/jobs/ routes — ported from Go jobshandler.go."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.jobs_routes import (
    get_job_service,
    get_request_context_dep,
    router as jobs_router,
)
from src.domain.job import Job
from src.services.job_service import JobService
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Fake JobDatastore — stub for testing
# ---------------------------------------------------------------------------

class FakeJobDatastore:
    """In-memory stub implementing the JobDatastore protocol for jobs tests."""

    def __init__(self) -> None:
        self.jobs_to_return: list[Job] = []
        self.last_kind: str = ""
        self.last_params: dict[str, Any] = {}

    def create_job(self) -> Job:
        return Job()

    def get_job(self, job_id: int) -> Job | None:
        return None

    def get_jobs(self, kind: str, parameters: dict[str, Any]) -> list[Job]:
        self.last_kind = kind
        self.last_params = parameters
        return self.jobs_to_return

    async def add_job(self, job: Job) -> None:
        pass

    async def update_job(self, job: Job) -> None:
        pass

    async def delete_job(self, job_id: int) -> tuple[Job | None, str | None]:
        return None, None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(fake_store: FakeJobDatastore) -> FastAPI:
    """Build a fresh FastAPI app wired to the fake store."""
    test_app = FastAPI()
    test_app.include_router(jobs_router, prefix="/api")

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
# GET /jobs/ — list jobs
# ===========================================================================

class TestGetJobs:
    async def test_get_jobs_success(self, client, fake_store):
        fake_store.jobs_to_return = [
            Job(id=1, kind="pcap"),
            Job(id=2, kind="analyze"),
        ]
        resp = await client.get("/api/jobs/", params={"kind": "pcap"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[1]["id"] == 2
        assert fake_store.last_kind == "pcap"

    async def test_get_jobs_empty(self, client, fake_store):
        fake_store.jobs_to_return = []
        resp = await client.get("/api/jobs/", params={"kind": ""})
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_jobs_with_parameters(self, client, fake_store):
        fake_store.jobs_to_return = [Job(id=3, kind="analyze")]
        params_json = json.dumps({"artifact": {"id": "abc123"}})
        resp = await client.get(
            "/api/jobs/",
            params={"kind": "analyze", "parameters": params_json},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert fake_store.last_params == {"artifact": {"id": "abc123"}}

    async def test_get_jobs_invalid_parameters(self, client):
        resp = await client.get(
            "/api/jobs/",
            params={"kind": "pcap", "parameters": "not-valid-json"},
        )
        assert resp.status_code == 400
