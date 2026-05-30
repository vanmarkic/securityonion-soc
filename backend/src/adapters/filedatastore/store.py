"""FileDatastore — file-based persistence for jobs and nodes.

Ported from Go server/modules/filedatastore/filedatastoreimpl.go.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.domain.job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_DELETED,
    JOB_STATUS_INCOMPLETE,
    Job,
    new_job,
)
from src.domain.node import NODE_STATUS_OK, Node

logger = logging.getLogger(__name__)

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_-]")
INITIAL_JOB_ID = 1001


def _sanitize(value: str) -> str:
    return _SANITIZE_RE.sub("_", value)


class FileDatastore:
    def __init__(
        self,
        job_dir: str,
        retry_failure_interval_ms: int = 600_000,
        retry_failure_max_attempts: int = 5,
        job_poll_retry_interval_ms: int = 0,
    ) -> None:
        self._job_dir = job_dir
        self._jobs_by_id: dict[int, Job] = {}
        self._nodes_by_id: dict[str, Node] = {}
        self._next_job_id = INITIAL_JOB_ID
        self._retry_failure_interval_ms = retry_failure_interval_ms
        self._retry_failure_max_attempts = retry_failure_max_attempts
        self._job_poll_retry_interval_ms = job_poll_retry_interval_ms
        # node_id-lowercased job-poll throttle: jobId -> last time it was handed out.
        self._job_process_time: dict[int, datetime] = {}

        os.makedirs(self._job_dir, exist_ok=True)

    def create_job(self) -> Job:
        job = new_job()
        job.id = self._next_job_id
        self._next_job_id += 1
        self._jobs_by_id[job.id] = job
        return job

    def get_job(self, job_id: int) -> Job | None:
        return self._jobs_by_id.get(job_id)

    def get_jobs(self, kind: str, parameters: dict[str, Any]) -> list[Job]:
        result: list[Job] = []
        for job in self._jobs_by_id.values():
            if job.status == JOB_STATUS_DELETED:
                continue
            if kind and job.get_kind() != kind:
                continue
            result.append(job)
        return result

    async def add_job(self, job: Job) -> None:
        self._jobs_by_id[job.id] = job
        self._save_job(job)

    async def update_job(self, job: Job) -> None:
        if job.id not in self._jobs_by_id:
            return
        self._jobs_by_id[job.id] = job
        self._save_job(job)

    async def delete_job(self, job_id: int) -> tuple[Job | None, None] | tuple[None, str]:
        job = self._jobs_by_id.pop(job_id, None)
        if job is None:
            return None, "Job not found"
        job.status = JOB_STATUS_DELETED
        self._delete_job_files(job)
        return job, None

    async def get_nodes(self) -> list[Node]:
        return list(self._nodes_by_id.values())

    def add_node(self, node: Node) -> None:
        """Insert a node directly (setup helper; the check-in path is update_node)."""
        self._nodes_by_id[node.id] = node

    async def update_node(self, node: Node) -> Node:
        """Record a node check-in. Ported from Go FileDatastoreImpl.UpdateNode.

        Copies only the fields the agent reports (epoch_time, role, description,
        mgmt_mac, address, version) onto the stored node, preserving everything
        else; creates the node if it is unknown; marks it connected and refreshes
        update_time/uptime. Nodes with an empty id are not stored (matches Go,
        which logs and skips). The licensing.ValidateMgmtMac call has no analogue
        in the rewrite and is intentionally omitted.
        """
        if not node.id:
            logger.info("Not adding node with missing id")
            return node

        existing = self._nodes_by_id.get(node.id)
        if existing is None:
            existing = node
            self._nodes_by_id[node.id] = existing

        existing.epoch_time = node.epoch_time
        existing.role = node.role
        existing.description = node.description
        existing.mgmt_mac = node.mgmt_mac
        existing.address = node.address
        existing.version = node.version
        existing.set_model(node.model)
        existing.connection_status = NODE_STATUS_OK
        existing.update_time = datetime.now(UTC)
        existing.uptime_seconds = int(
            (existing.update_time - existing.online_time).total_seconds()
        )
        return existing

    def get_next_job(self, node_id: str) -> Job | None:
        """Return the oldest eligible job for a node. Ported from Go GetNextJob.

        Skips completed jobs, incomplete jobs that are not yet retry-eligible, and
        jobs handed out within job_poll_retry_interval_ms (throttle disabled when 0).
        Records the poll time of the job it returns.
        """
        target = node_id.lower()
        now = datetime.now(UTC)
        throttle = timedelta(milliseconds=self._job_poll_retry_interval_ms)
        next_job: Job | None = None

        for job in self._jobs_by_id.values():
            if job.get_node_id().lower() != target:
                continue
            if (
                job.status != JOB_STATUS_COMPLETED
                and (next_job is None or job.create_time < next_job.create_time)
                and (
                    job.status != JOB_STATUS_INCOMPLETE
                    or job.is_eligible_for_retry(
                        self._retry_failure_interval_ms,
                        self._retry_failure_max_attempts,
                    )
                )
            ):
                last_poll = self._job_process_time.get(job.id)
                if last_poll is not None and (now - last_poll) < throttle:
                    continue
                next_job = job

        if next_job is not None:
            self._job_process_time[next_job.id] = now
        return next_job

    def _job_dir_for(self, job: Job) -> Path:
        node_id = job.get_node_id()
        node_dir = _sanitize(node_id) if node_id else "_default"
        return Path(self._job_dir) / node_dir

    def _job_path(self, job: Job) -> Path:
        return self._job_dir_for(job) / f"{job.id}.json"

    def _save_job(self, job: Job) -> None:
        path = self._job_path(job)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(job.model_dump_json(by_alias=True))

    def _delete_job_files(self, job: Job) -> None:
        # Build sibling paths from the job id stem. We cannot use
        # Path.with_suffix(".bin.unwrapped") because it only replaces the final
        # suffix (yielding "1001.unwrapped", not "1001.bin.unwrapped").
        directory = self._job_dir_for(job)
        for name in (f"{job.id}.json", f"{job.id}.bin", f"{job.id}.bin.unwrapped"):
            target = directory / name
            if target.exists():
                target.unlink()
