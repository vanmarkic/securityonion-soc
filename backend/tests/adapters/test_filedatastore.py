"""Tests for FileDatastore adapter — ported from Go filedatastoreimpl_test.go."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.adapters.filedatastore.store import FileDatastore
from src.domain.job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_INCOMPLETE,
    JOB_STATUS_PENDING,
)
from src.domain.node import NODE_STATUS_OK, Node


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

    async def test_update_node_copies_fields_and_marks_ok(self, store: FileDatastore):
        incoming = Node("node-a")
        incoming.role = "so-sensor"
        incoming.description = "Sensor A"
        incoming.address = "10.0.0.5"
        incoming.version = "2.4.0"
        incoming.mgmt_mac = "aa:bb:cc:dd:ee:ff"

        result = await store.update_node(incoming)

        assert result.connection_status == NODE_STATUS_OK
        assert result.role == "so-sensor"
        assert result.description == "Sensor A"
        assert result.address == "10.0.0.5"
        assert result.version == "2.4.0"
        assert result.mgmt_mac == "aa:bb:cc:dd:ee:ff"
        # The node is now retrievable from the store.
        nodes = await store.get_nodes()
        assert len(nodes) == 1
        assert nodes[0].id == "node-a"

    async def test_update_node_preserves_online_time_and_computes_uptime(
        self, store: FileDatastore
    ):
        first = Node("node-b")
        first.online_time = datetime.now(UTC) - timedelta(seconds=60)
        store.add_node(first)

        incoming = Node("node-b")
        incoming.description = "checkin"
        result = await store.update_node(incoming)

        # online_time is preserved from the stored node; uptime derives from it.
        assert result.online_time == first.online_time
        assert result.uptime_seconds >= 60

    async def test_update_node_preserves_unlisted_fields(self, store: FileDatastore):
        existing = Node("node-c")
        existing.grid_id = "grid-1"
        store.add_node(existing)

        incoming = Node("node-c")
        incoming.description = "new desc"
        result = await store.update_node(incoming)

        assert result.description == "new desc"
        # grid_id is not part of the copied field set, so it is preserved.
        assert result.grid_id == "grid-1"

    async def test_update_node_empty_id_not_stored(self, store: FileDatastore):
        result = await store.update_node(Node(""))
        assert result.id == ""
        assert await store.get_nodes() == []


class TestGetNextJob:
    def _job(
        self,
        store: FileDatastore,
        node_id: str,
        *,
        status: int = JOB_STATUS_PENDING,
        create_time: datetime | None = None,
    ):
        job = store.create_job()
        job.node_id = node_id
        job.status = status
        if create_time is not None:
            job.create_time = create_time
        return job

    def test_returns_none_when_no_jobs(self, store: FileDatastore):
        assert store.get_next_job("node-x") is None

    def test_returns_pending_job_for_node(self, store: FileDatastore):
        job = self._job(store, "node-x")
        assert store.get_next_job("node-x") is job

    def test_skips_completed_jobs(self, store: FileDatastore):
        self._job(store, "node-x", status=JOB_STATUS_COMPLETED)
        assert store.get_next_job("node-x") is None

    def test_ignores_jobs_for_other_nodes(self, store: FileDatastore):
        self._job(store, "node-y")
        assert store.get_next_job("node-x") is None

    def test_returns_oldest_eligible_first(self, store: FileDatastore):
        now = datetime.now(UTC)
        self._job(store, "node-x", create_time=now)
        older = self._job(store, "node-x", create_time=now - timedelta(minutes=5))
        assert store.get_next_job("node-x") is older

    def test_node_id_is_case_insensitive(self, store: FileDatastore):
        job = self._job(store, "node-x")
        assert store.get_next_job("NODE-X") is job

    def test_incomplete_eligible_for_retry_is_returned(self, store: FileDatastore):
        job = self._job(store, "node-x", status=JOB_STATUS_INCOMPLETE)
        job.fail_time = datetime.now(UTC) - timedelta(hours=1)
        job.fail_count = 1
        assert store.get_next_job("node-x") is job

    def test_incomplete_not_eligible_is_skipped(self, store: FileDatastore):
        job = self._job(store, "node-x", status=JOB_STATUS_INCOMPLETE)
        job.fail_time = datetime.now(UTC) - timedelta(hours=1)
        job.fail_count = 99
        assert store.get_next_job("node-x") is None

    def test_recently_polled_job_is_throttled(self, tmp_path: Path):
        store = FileDatastore(
            job_dir=str(tmp_path / "jobs"), job_poll_retry_interval_ms=600_000
        )
        job = store.create_job()
        job.node_id = "node-x"
        # First poll hands out the job and records the poll time.
        assert store.get_next_job("node-x") is job
        # Second poll within the interval is throttled.
        assert store.get_next_job("node-x") is None
