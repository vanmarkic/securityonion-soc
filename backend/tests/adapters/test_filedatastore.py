"""Tests for FileDatastore adapter — ported from Go filedatastoreimpl_test.go."""

from pathlib import Path

import pytest

from src.adapters.filedatastore.store import FileDatastore
from src.domain.job import JOB_STATUS_COMPLETED, JOB_STATUS_PENDING
from src.domain.node import Node


@pytest.fixture
def store(tmp_path: Path) -> FileDatastore:
    return FileDatastore(job_dir=str(tmp_path / "jobs"))


class TestCreateJob:
    def test_first_job_id_is_1001(self, store: FileDatastore):
        job = store.create_job()
        assert job.id == 1001

    def test_ids_auto_increment(self, store: FileDatastore):
        j1 = store.create_job()
        j2 = store.create_job()
        assert j1.id == 1001
        assert j2.id == 1002

    def test_new_job_is_pending(self, store: FileDatastore):
        job = store.create_job()
        assert job.status == JOB_STATUS_PENDING


class TestGetJob:
    def test_get_existing_job(self, store: FileDatastore):
        job = store.create_job()
        found = store.get_job(job.id)
        assert found is not None
        assert found.id == job.id

    def test_get_missing_job_returns_none(self, store: FileDatastore):
        assert store.get_job(9999) is None


class TestGetJobs:
    async def test_get_all_jobs(self, store: FileDatastore):
        j1 = store.create_job()
        j2 = store.create_job()
        await store.add_job(j1)
        await store.add_job(j2)
        jobs = store.get_jobs("", {})
        assert len(jobs) == 2

    async def test_filter_by_kind(self, store: FileDatastore):
        j1 = store.create_job()
        j1.kind = "pcap"
        j2 = store.create_job()
        j2.kind = "reports"
        await store.add_job(j1)
        await store.add_job(j2)
        pcap_jobs = store.get_jobs("pcap", {})
        assert len(pcap_jobs) == 1
        assert pcap_jobs[0].kind == "pcap"


class TestAddJob:
    async def test_add_persists_to_disk(self, store: FileDatastore, tmp_path: Path):
        job = store.create_job()
        job.node_id = "test-node"
        await store.add_job(job)

        job_dir = tmp_path / "jobs"
        json_files = list(job_dir.rglob("*.json"))
        assert len(json_files) == 1

    async def test_add_sets_status_pending(self, store: FileDatastore):
        job = store.create_job()
        await store.add_job(job)
        found = store.get_job(job.id)
        assert found is not None
        assert found.status == JOB_STATUS_PENDING


class TestUpdateJob:
    async def test_update_changes_status(self, store: FileDatastore):
        job = store.create_job()
        await store.add_job(job)
        job.complete()
        await store.update_job(job)
        found = store.get_job(job.id)
        assert found is not None
        assert found.status == JOB_STATUS_COMPLETED


class TestDeleteJob:
    async def test_delete_existing(self, store: FileDatastore):
        job = store.create_job()
        await store.add_job(job)
        result = await store.delete_job(job.id)
        assert result[0] is not None
        assert result[1] is None
        assert store.get_job(job.id) is None

    async def test_delete_missing(self, store: FileDatastore):
        result = await store.delete_job(9999)
        assert result[0] is None
        assert result[1] is not None

    async def test_delete_removes_all_sibling_files(self, store: FileDatastore, tmp_path: Path):
        job = store.create_job()
        job.node_id = "test-node"
        await store.add_job(job)

        # Simulate the binary artifacts that accompany a job on disk.
        job_dir = tmp_path / "jobs" / "test-node"
        (job_dir / f"{job.id}.bin").write_bytes(b"payload")
        (job_dir / f"{job.id}.bin.unwrapped").write_bytes(b"unwrapped")

        await store.delete_job(job.id)

        assert list(job_dir.glob(f"{job.id}*")) == []


class TestNodes:
    async def test_add_and_get_nodes(self, store: FileDatastore):
        node = Node("test-node-1")
        node.description = "Test node"
        store.add_node(node)
        nodes = await store.get_nodes()
        assert len(nodes) == 1
        assert nodes[0].id == "test-node-1"

    async def test_update_node(self, store: FileDatastore):
        node = Node("test-node-1")
        node.description = "Original"
        store.add_node(node)
        node.description = "Updated"
        store.update_node(node)
        nodes = await store.get_nodes()
        assert nodes[0].description == "Updated"
