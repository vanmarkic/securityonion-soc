"""FileDatastore — file-based persistence for jobs and nodes.

Ported from Go server/modules/filedatastore/filedatastoreimpl.go.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from src.domain.job import JOB_STATUS_DELETED, Job, new_job
from src.domain.node import Node

logger = logging.getLogger(__name__)

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_-]")
INITIAL_JOB_ID = 1001


def _sanitize(value: str) -> str:
    return _SANITIZE_RE.sub("_", value)


class FileDatastore:
    def __init__(self, job_dir: str) -> None:
        self._job_dir = job_dir
        self._jobs_by_id: dict[int, Job] = {}
        self._nodes_by_id: dict[str, Node] = {}
        self._next_job_id = INITIAL_JOB_ID

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
        self._nodes_by_id[node.id] = node

    def update_node(self, node: Node) -> None:
        self._nodes_by_id[node.id] = node

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
