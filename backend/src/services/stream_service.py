"""StreamService — business logic for stream (job output) endpoints."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class StreamDatastore(Protocol):
    """Protocol for the stream data backend."""

    async def get_job_stream(
        self, job_id: int, unwrap: bool,
    ) -> tuple[bytes | None, str, int, str]: ...

    async def save_job_stream(self, job_id: int, data: bytes) -> None: ...


class StreamService:
    """Service layer for stream operations."""

    def __init__(self, datastore: StreamDatastore) -> None:
        self._datastore = datastore

    async def get_job_stream(
        self, job_id: int, unwrap: bool,
    ) -> tuple[bytes | None, str, int, str]:
        """Retrieve a job output stream.

        Returns (content_bytes_or_None, filename, length, mime_type).
        """
        return await self._datastore.get_job_stream(job_id, unwrap)

    async def save_job_stream(self, job_id: int, data: bytes) -> None:
        """Save job output stream data."""
        await self._datastore.save_job_stream(job_id, data)
