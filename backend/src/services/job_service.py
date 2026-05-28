"""JobService — business logic for job CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from src.domain.job import Job
from src.ports.jobs import JobDatastore

logger = logging.getLogger(__name__)


class JobNotFoundError(Exception):
    """Raised when a job is not found."""


class JobService:
    """Business logic for job-related endpoints."""

    def __init__(self, datastore: JobDatastore) -> None:
        self._store = datastore

    def get_job(self, job_id: int) -> Job | None:
        return self._store.get_job(job_id)

    def get_jobs(self, kind: str, parameters: dict[str, Any]) -> list[Job]:
        return self._store.get_jobs(kind, parameters)

    def create_job(self) -> Job:
        return self._store.create_job()

    async def add_job(self, job: Job) -> None:
        await self._store.add_job(job)

    async def update_job(self, job: Job) -> None:
        await self._store.update_job(job)

    async def delete_job(self, job_id: int) -> tuple[Job | None, str | None]:
        return await self._store.delete_job(job_id)
