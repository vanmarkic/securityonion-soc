"""Datastore port (job-related) — defines the contract for job persistence."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.domain.job import Job


@runtime_checkable
class JobDatastore(Protocol):
    """Protocol that any job-storing adapter must satisfy."""

    def create_job(self) -> Job: ...

    def get_job(self, job_id: int) -> Job | None: ...

    def get_jobs(self, kind: str, parameters: dict[str, Any]) -> list[Job]: ...

    async def add_job(self, job: Job) -> None: ...

    async def update_job(self, job: Job) -> None: ...

    async def delete_job(self, job_id: int) -> tuple[Job | None, None] | tuple[None, str]: ...
